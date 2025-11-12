#!/usr/bin/env python3
"""
Utility script to bulk-load Synthea FHIR NDJSON into an Azure FHIR workspace.

Steps performed:
1. Upload every *.ndjson file from the provided directory to a blob container.
2. Trigger the FHIR $import operation so the service ingests the uploaded data.
3. (Optional) Poll the import status until completion.

Requirements:
- FHIR_URL must be set (or passed via --fhir-url)
- Container SAS URL with read/write/list rights via env FHIR_IMPORT_CONTAINER_SAS_URL or --container-url
- User/application identity must have rights to call the FHIR service.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient
from dotenv import load_dotenv


NdjsonUpload = Tuple[Path, str, str]


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


def infer_resource_type(file_path: Path) -> str:
    """Infer the FHIR resource type from the filename."""
    stem = file_path.stem
    return stem.split("_", maxsplit=1)[0]


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
    input_dir, container_url, fhir_url = validate_inputs(args)
    files = discover_ndjson_files(input_dir, args.resource_types)

    prefix = args.prefix or f"synthea-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    container_client = ContainerClient.from_container_url(container_url)

    if args.skip_upload:
        if not args.prefix:
            sys.exit("--prefix is required when using --skip-upload to specify the blob folder.")
        print(f"Skipping upload. Assuming {len(files)} NDJSON files exist in {container_url} under prefix '{prefix}'")
        # Construct uploads list without actually uploading
        uploads = [(local_path, f"{prefix}/{local_path.name}", resource_type)
                   for local_path, resource_type in files]
    else:
        print(f"Uploading {len(files)} NDJSON files to {container_url} under prefix '{prefix}'")
        uploads = upload_files(container_client, files, prefix)

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False)
    status_url = trigger_import(credential, fhir_url, container_url, uploads)

    if args.wait:
        poll_import_status(credential, fhir_url,
                           status_url, args.poll_interval)
    else:
        print("Run with --wait to poll import status automatically.")


if __name__ == "__main__":
    main()
