#!/usr/bin/env python3
"""
Utility script to bulk-load Synthea FHIR NDJSON into an Azure FHIR workspace.

Steps performed:
1. Rewrite conditional references (e.g., `Patient?identifier=`) to fixed `ResourceType/id` links, deduplicate repeated records, and stage sanitized NDJSON files.
2. Upload every staged *.ndjson file to a blob container.
3. Trigger a first $import pass for base resources (Patient, Organization, Practitioner) and wait for completion.
4. Trigger a second $import pass for dependent resources (Encounter, Observation, etc.) and optionally poll until completion.

Requirements:
- FHIR_URL must be set (or passed via --fhir-url)
- Container SAS URL with read/write/list rights via env FHIR_IMPORT_CONTAINER_SAS_URL or --container-url
- User/application identity must have rights to call the FHIR service.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient
from dotenv import load_dotenv
from azure.core.exceptions import ResourceExistsError, HttpResponseError


NdjsonUpload = Tuple[Path, str, str]
IdentifierKey = Tuple[str, str, str]
BASE_RESOURCE_TYPES = {"patient", "organization", "practitioner"}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Load Synthea-generated NDJSON files into an Azure FHIR workspace."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Path to the folder containing *.ndjson exports from Synthea.",
    )
    parser.add_argument(
        "--container-url",
        default=os.environ.get("FHIR_IMPORT_CONTAINER_SAS_URL"),
        help="Azure Blob container SAS URL used for staging import files.",
    )
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("FHIR_URL"),
        help="Azure FHIR service URL (e.g., https://workspace-service.fhir.azurehealthcareapis.com).",
    )
    parser.add_argument(
        "--prefix",
        help="Blob prefix/folder to place uploads under. Defaults to synthea-<timestamp>.",
    )
    parser.add_argument(
        "--resource-types",
        nargs="+",
        help="Optional allow list of FHIR resource types to upload (e.g., Patient Encounter Observation).",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip uploading files (assumes files are already in blob storage at the specified prefix).",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll the $import operation until completion.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling interval in seconds when --wait is supplied (default: 30).",
    )
    return parser.parse_args()


def validate_inputs(args: argparse.Namespace) -> Tuple[Path, str, str]:
    """Ensure directories and URLs are present."""
    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        sys.exit(f"Input directory not found: {input_dir}")

    if not args.container_url:
        sys.exit(
            "Missing container SAS URL. Set FHIR_IMPORT_CONTAINER_SAS_URL or pass --container-url.")

    if not args.fhir_url:
        sys.exit("Missing FHIR service URL. Set FHIR_URL or pass --fhir-url.")

    return input_dir, args.container_url.rstrip("/"), args.fhir_url.rstrip("/")


def discover_ndjson_files(
    input_dir: Path, allow_types: Sequence[str] | None
) -> List[Tuple[Path, str]]:
    """Locate *.ndjson files and map them to resource types."""
    files: List[Tuple[Path, str]] = []
    normalized_allow = {rt.lower()
                        for rt in allow_types} if allow_types else None

    for file_path in sorted(input_dir.glob("*.ndjson")):
        resource_type = infer_resource_type(file_path)
        if normalized_allow and resource_type.lower() not in normalized_allow:
            continue
        files.append((file_path, resource_type))

    if not files:
        msg = "No NDJSON files discovered"
        if allow_types:
            msg += f" for resource types {', '.join(allow_types)}"
        sys.exit(f"{msg} in {input_dir}")

    return files


def partition_files_by_stage(files: Sequence[Tuple[Path, str]]) -> Tuple[List[Tuple[Path, str]], List[Tuple[Path, str]]]:
    """Split NDJSON files into base (stage 1) and dependent (stage 2) sets."""
    base_files: List[Tuple[Path, str]] = []
    dependent_files: List[Tuple[Path, str]] = []

    for file_path, resource_type in files:
        if resource_type.lower() in BASE_RESOURCE_TYPES:
            base_files.append((file_path, resource_type))
        else:
            dependent_files.append((file_path, resource_type))

    return base_files, dependent_files


def iter_ndjson_resources(path: Path) -> Iterable[Dict]:
    """Yield JSON objects from an NDJSON file."""
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as exc:
                sys.exit(f"Failed to parse JSON in {path} at line {line_number}: {exc}")


def collect_identifier_index(
    files: Sequence[Tuple[Path, str]]
) -> Tuple[Dict[IdentifierKey, str], Dict[str, str]]:
    """Build lookup tables for identifier->resource ID resolution."""
    index: Dict[IdentifierKey, str] = {}
    canonical_types: Dict[str, str] = {}

    for file_path, fallback_type in files:
        for resource in iter_ndjson_resources(file_path):
            resource_type = (resource.get("resourceType") or fallback_type or "").strip()
            if not resource_type:
                continue
            resource_key = resource_type.lower()
            canonical_types.setdefault(resource_key, resource_type)

            resource_id = resource.get("id")
            if not resource_id:
                continue
            # Allow matching purely by resource ID if references already conform.
            index.setdefault((resource_key, "", resource_id), resource_id)

            for system, value in extract_identifier_values(resource.get("identifier")):
                if not value:
                    continue
                sys_key = system or ""
                key_with_system = (resource_key, sys_key, value)
                key_without_system = (resource_key, "", value)
                index.setdefault(key_with_system, resource_id)
                index.setdefault(key_without_system, resource_id)

    if not index:
        print("Warning: no identifiers discovered while preprocessing; reference fixing may be limited.")

    return index, canonical_types


def extract_identifier_values(identifier_field: object) -> Iterable[Tuple[str | None, str | None]]:
    """Yield (system, value) pairs from an identifier attribute."""
    if isinstance(identifier_field, dict):
        yield identifier_field.get("system"), identifier_field.get("value")
    elif isinstance(identifier_field, list):
        for entry in identifier_field:
            if isinstance(entry, dict):
                yield entry.get("system"), entry.get("value")


def preprocess_ndjson_files(
    files: Sequence[Tuple[Path, str]],
    staging_dir: Path,
    identifier_index: Dict[IdentifierKey, str],
    canonical_types: Dict[str, str],
) -> Tuple[List[Tuple[Path, str]], int, int, int]:
    """Rewrite conditional references and emit sanitized NDJSON files in staging_dir."""
    processed: List[Tuple[Path, str]] = []
    total_resolved = 0
    total_unresolved = 0
    total_skipped = 0
    seen_ids: Dict[str, set[str]] = {}

    staging_dir.mkdir(parents=True, exist_ok=True)
    for original_path, resource_type in files:
        staged_path = staging_dir / original_path.name
        resolved, unresolved, skipped = rewrite_ndjson_file(
            original_path, staged_path, identifier_index, canonical_types, seen_ids
        )
        total_resolved += resolved
        total_unresolved += unresolved
        total_skipped += skipped
        processed.append((staged_path, resource_type))

    return processed, total_resolved, total_unresolved, total_skipped


def rewrite_ndjson_file(
    source_path: Path,
    target_path: Path,
    identifier_index: Dict[IdentifierKey, str],
    canonical_types: Dict[str, str],
    seen_ids: Dict[str, set[str]],
) -> Tuple[int, int, int]:
    """Rewrite a single NDJSON file, returning (resolved_refs, unresolved_refs, skipped_duplicates)."""
    resolved = 0
    unresolved = 0
    skipped = 0

    with source_path.open("r", encoding="utf-8") as reader, target_path.open("w", encoding="utf-8") as writer:
        for line_number, line in enumerate(reader, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                resource = json.loads(stripped)
            except json.JSONDecodeError as exc:
                sys.exit(f"Failed to parse JSON in {source_path} at line {line_number}: {exc}")

            resource_type = (resource.get("resourceType") or "").strip().lower()
            resource_id = (resource.get("id") or "").strip()
            if resource_type and resource_id:
                seen = seen_ids.setdefault(resource_type, set())
                if resource_id in seen:
                    skipped += 1
                    continue
                seen.add(resource_id)

            ref_resolved, ref_unresolved = rewrite_resource_references(resource, identifier_index, canonical_types)
            resolved += ref_resolved
            unresolved += ref_unresolved
            writer.write(json.dumps(resource))
            writer.write("\n")

    return resolved, unresolved, skipped


def rewrite_resource_references(
    resource: Dict,
    identifier_index: Dict[IdentifierKey, str],
    canonical_types: Dict[str, str],
) -> Tuple[int, int]:
    """Walk a resource in-place, rewriting conditional references."""
    resolved = 0
    unresolved = 0

    def _walk(node: object) -> None:
        nonlocal resolved, unresolved
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "reference" and isinstance(value, str):
                    new_value, did_resolve, attempted = rewrite_reference_value(value, identifier_index, canonical_types)
                    if did_resolve:
                        node[key] = new_value
                        resolved += 1
                    elif attempted:
                        unresolved += 1
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(resource)
    return resolved, unresolved


def rewrite_reference_value(
    reference: str,
    identifier_index: Dict[IdentifierKey, str],
    canonical_types: Dict[str, str],
) -> Tuple[str, bool, bool]:
    """Return (new_reference, resolved, attempted) for a reference string."""
    parts = split_reference(reference)
    if not parts:
        return reference, False, False

    resource_segment, query = parts
    params = parse_qs(query, keep_blank_values=True)
    identifiers = params.get("identifier")
    if not identifiers:
        return reference, False, False

    token = identifiers[0]
    if not token:
        return reference, False, True

    if "|" in token:
        system, value = token.split("|", 1)
    else:
        system, value = "", token

    resource_key = resource_segment.lower()
    lookup_keys = [
        (resource_key, system, value),
        (resource_key, "", value) if system else None,
    ]

    target_id = None
    for key in lookup_keys:
        if key and key in identifier_index:
            target_id = identifier_index[key]
            break

    if not target_id:
        return reference, False, True

    canonical_type = canonical_types.get(resource_key, resource_segment)
    canonical_type = canonical_type.split("/")[-1]
    return f"{canonical_type}/{target_id}", True, True


def split_reference(reference: str) -> Tuple[str, str] | None:
    """Split a reference into (resource_segment, query) if it contains a conditional search."""
    if "?" not in reference:
        return None

    if reference.startswith(("http://", "https://")):
        parsed = urlparse(reference)
        resource_segment = parsed.path.rstrip("/").split("/")[-1]
        query = parsed.query
    else:
        resource_part, query = reference.split("?", 1)
        resource_segment = resource_part.rstrip("/").split("/")[-1]

    if not resource_segment or not query:
        return None
    return resource_segment, query


def infer_resource_type(file_path: Path) -> str:
    """Infer the FHIR resource type from the filename."""
    stem = file_path.stem
    resource_type = stem.split("_", maxsplit=1)[0]
    # Preserve casing from filenames such as MedicationRequest.ndjson
    return resource_type


def ensure_container_exists(container_client: ContainerClient) -> None:
    """Create the target container if it is missing."""
    try:
        container_client.create_container()
        print("Created target blob container.")
    except ResourceExistsError:
        # Container already present; nothing to do.
        return
    except HttpResponseError as exc:
        # Surface permission issues up front to avoid repeated upload failures.
        if exc.status_code == 409 and "ContainerAlreadyExists" in str(exc):
            return
        sys.exit(f"Failed to ensure blob container exists: {exc}")


def upload_files(
    container_client: ContainerClient,
    files: Sequence[Tuple[Path, str]],
    prefix: str,
) -> List[NdjsonUpload]:
    """Upload NDJSON files and return metadata for the import operation."""
    uploaded: List[NdjsonUpload] = []
    for local_path, resource_type in files:
        blob_name = f"{prefix}/{local_path.name}"
        print(f"Uploading {local_path.name} as {blob_name} ({resource_type})")
        with local_path.open("rb") as data:
            container_client.upload_blob(
                name=blob_name, data=data, overwrite=True)

        uploaded.append((local_path, blob_name, resource_type))

    return uploaded


def trigger_import(
    credential: DefaultAzureCredential,
    fhir_url: str,
    container_url: str,
    uploads: Sequence[NdjsonUpload],
) -> str:
    """Call the $import endpoint and return the status URL."""
    if not uploads:
        sys.exit("No uploads staged for import.")

    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
        "Prefer": "respond-async",
    }

    # Build Parameters resource for Azure FHIR $import
    # Extract base container URL (remove SAS token)
    base_container_url = container_url.split('?')[0]

    input_params = []
    for _, blob_name, resource_type in uploads:
        # Construct full blob URL
        blob_url = f"{base_container_url}/{blob_name}"
        input_params.append({
            "name": "input",
            "part": [
                {"name": "type", "valueString": resource_type},
                {"name": "url", "valueUri": blob_url}
            ]
        })

    payload: Dict[str, object] = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "inputFormat", "valueString": "application/fhir+ndjson"},
            {"name": "mode", "valueString": "InitialLoad"},
            {"name": "inputSource", "valueUri": container_url},
            *input_params
        ]
    }

    print("Starting $import operation...")
    response = requests.post(f"{fhir_url}/$import",
                             headers=headers, json=payload, timeout=30)
    if response.status_code not in {200, 202}:
        sys.exit(f"$import failed: {response.status_code} {response.text}")

    status_url = response.headers.get("Content-Location")
    if not status_url:
        sys.exit(
            "FHIR service did not return a Content-Location header for status polling.")

    print(f"$import accepted. Status URL: {status_url}")
    return status_url


def poll_import_status(
    credential: DefaultAzureCredential,
    fhir_url: str,
    status_url: str,
    interval_seconds: int,
) -> None:
    """Poll the import status endpoint until completion."""
    print("Polling import status...")
    scope = f"{fhir_url}/.default"
    while True:
        access_token = credential.get_token(scope).token
        headers = {"Authorization": f"Bearer {access_token}",
                   "Accept": "application/json"}
        response = requests.get(status_url, headers=headers, timeout=30)

        if response.status_code == 200:
            print("Import completed successfully.")
            print(response.text)
            return

        if response.status_code >= 400:
            sys.exit(
                f"$import status failed: {response.status_code} {response.text}")

        retry_after = int(response.headers.get(
            "Retry-After", interval_seconds))
        print(
            f"Import still running (status {response.status_code}). Waiting {retry_after}s...")
        time.sleep(retry_after)


def main() -> None:
    load_dotenv()
    args = parse_args()
    if args.skip_upload:
        sys.exit("--skip-upload is not supported because preprocessing rewrites NDJSON locally before upload.")
    input_dir, container_url, fhir_url = validate_inputs(args)
    discovered_files = discover_ndjson_files(input_dir, args.resource_types)
    identifier_index, canonical_types = collect_identifier_index(discovered_files)

    with tempfile.TemporaryDirectory(prefix="synthea-preprocessed-") as tmpdir:
        staging_dir = Path(tmpdir)
        processed_files, resolved_refs, unresolved_refs, skipped_dupes = preprocess_ndjson_files(
            discovered_files, staging_dir, identifier_index, canonical_types
        )
        print(
            f"Preprocessed NDJSON files in {staging_dir}: resolved {resolved_refs} conditional references; "
            f"{unresolved_refs} unresolved; skipped {skipped_dupes} duplicate resources."
        )
        if unresolved_refs:
            print(
                "Warning: some conditional references could not be resolved; they remain unchanged and may fail import.",
                file=sys.stderr,
            )

        base_files, dependent_files = partition_files_by_stage(processed_files)
        print(
            f"Discovered {len(base_files)} base resource files and {len(dependent_files)} dependent resource files."
        )

        prefix = args.prefix or f"synthea-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Check if container URL has SAS token (contains '?')
        # If not, use managed identity for authentication
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

        if '?' in container_url:
            print("Using SAS token authentication for blob storage")
            container_client = ContainerClient.from_container_url(container_url)
        else:
            print("Using managed identity authentication for blob storage")
            container_client = ContainerClient.from_container_url(
                container_url,
                credential=credential
            )
        ensure_container_exists(container_client)

        total_files = len(processed_files)
        print(f"Uploading {total_files} preprocessed NDJSON files to {container_url} under prefix '{prefix}'")
        stage_one_uploads = upload_files(container_client, base_files, prefix)
        stage_two_uploads = upload_files(container_client, dependent_files, prefix)

        def run_stage(stage_name: str, uploads: Sequence[NdjsonUpload], wait_for_completion: bool) -> str | None:
            if not uploads:
                print(f"{stage_name}: no files to import; skipping.")
                return None
            print(f"{stage_name}: importing {len(uploads)} files.")
            status = trigger_import(credential, fhir_url, container_url, uploads)
            if wait_for_completion:
                poll_import_status(credential, fhir_url, status, args.poll_interval)
            else:
                print("Run with --wait to poll import status automatically.")
            return status

        stage_one_status = run_stage("Stage 1 - base resources", stage_one_uploads, True)

        if stage_one_status:
            print("Stage 1 completed; proceeding to Stage 2 for dependent resources.")
        else:
            print("Stage 1 skipped. Continuing to Stage 2 (dependent resources).")

        run_stage("Stage 2 - dependent resources", stage_two_uploads, args.wait)


if __name__ == "__main__":
    main()
