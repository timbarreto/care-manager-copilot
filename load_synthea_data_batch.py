#!/usr/bin/env python3
"""
Load Synthea FHIR NDJSON into Azure FHIR workspace using FHIR batch API.

This script reads NDJSON files and uploads them using FHIR batch bundles,
which is an alternative to the bulk $import operation.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from tqdm import tqdm


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Load Synthea-generated NDJSON files into Azure FHIR workspace using batch API."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Path to the folder containing *.ndjson exports from Synthea.",
    )
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("FHIR_URL"),
        help="Azure FHIR service URL.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of resources per batch (default: 100).",
    )
    parser.add_argument(
        "--resource-types",
        nargs="+",
        help="Optional allow list of FHIR resource types to upload.",
    )
    return parser.parse_args()


def discover_ndjson_files(input_dir: Path, allow_types: List[str] | None) -> List[Path]:
    """Locate *.ndjson files."""
    files: List[Path] = []
    normalized_allow = {rt.lower() for rt in allow_types} if allow_types else None

    for file_path in sorted(input_dir.glob("*.ndjson")):
        resource_type = file_path.stem.split("_", maxsplit=1)[0]
        if normalized_allow and resource_type.lower() not in normalized_allow:
            continue
        files.append(file_path)

    if not files:
        msg = "No NDJSON files discovered"
        if allow_types:
            msg += f" for resource types {', '.join(allow_types)}"
        sys.exit(f"{msg} in {input_dir}")

    return files


def load_resources_from_ndjson(file_path: Path) -> List[dict]:
    """Load FHIR resources from an NDJSON file."""
    resources = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                resource = json.loads(line)
                resources.append(resource)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON at {file_path}:{line_num}: {e}")
    return resources


def create_batch_bundle(resources: List[dict]) -> dict:
    """Create a FHIR batch bundle from a list of resources."""
    entries = []
    for resource in resources:
        resource_type = resource.get('resourceType')
        resource_id = resource.get('id')
        if not resource_type or not resource_id:
            print(f"Warning: Skipping resource without type or ID: {resource}")
            continue

        entries.append({
            "request": {
                "method": "PUT",
                "url": f"{resource_type}/{resource_id}"
            },
            "resource": resource
        })

    return {
        "resourceType": "Bundle",
        "type": "batch",
        "entry": entries
    }


def upload_batch(fhir_url: str, credential: DefaultAzureCredential, bundle: dict) -> dict:
    """Upload a batch bundle to the FHIR server."""
    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }

    response = requests.post(fhir_url, headers=headers, json=bundle, timeout=60)

    if response.status_code not in {200, 201}:
        print(f"\nBatch upload failed: {response.status_code}")
        print(response.text[:500])
        raise Exception(f"Batch upload failed with status {response.status_code}")

    return response.json()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.fhir_url:
        sys.exit("Missing FHIR service URL. Set FHIR_URL or pass --fhir-url.")

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        sys.exit(f"Input directory not found: {input_dir}")

    fhir_url = args.fhir_url.rstrip("/")
    files = discover_ndjson_files(input_dir, args.resource_types)

    print(f"Found {len(files)} NDJSON files to process")
    print(f"FHIR Service: {fhir_url}")
    print(f"Batch size: {args.batch_size}")
    print("=" * 70)

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    total_resources = 0
    total_batches = 0

    for file_path in files:
        resource_type = file_path.stem.split("_", maxsplit=1)[0]
        print(f"\nProcessing {file_path.name} ({resource_type})...")

        resources = load_resources_from_ndjson(file_path)
        if not resources:
            print(f"  No resources found in {file_path.name}")
            continue

        print(f"  Loaded {len(resources)} resources")

        # Split into batches
        for i in tqdm(range(0, len(resources), args.batch_size), desc=f"  Uploading", unit="batch"):
            batch = resources[i:i + args.batch_size]
            bundle = create_batch_bundle(batch)

            try:
                result = upload_batch(fhir_url, credential, bundle)
                total_batches += 1
                total_resources += len(batch)

                # Check for errors in batch response
                if 'entry' in result:
                    errors = [e for e in result['entry'] if e.get('response', {}).get('status', '').startswith(('4', '5'))]
                    if errors:
                        print(f"\n  Warning: {len(errors)} resources failed in batch")
                        for error in errors[:3]:  # Show first 3 errors
                            print(f"    - {error.get('response', {}).get('status')}: {error.get('response', {}).get('outcome', {})}")

            except Exception as e:
                print(f"\n  Error uploading batch: {e}")
                continue

    print("\n" + "=" * 70)
    print(f"Upload complete!")
    print(f"Total resources uploaded: {total_resources}")
    print(f"Total batches: {total_batches}")
    print("=" * 70)


if __name__ == "__main__":
    main()
