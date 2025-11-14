#!/usr/bin/env python3
"""
Convert and load HL7v2 sample data using Azure FHIR $convert-data operation.

This script:
1. Loads sample HL7v2 messages (ADT_A01 and ORU_R01) for 2 patients
2. Converts each message to FHIR format using $convert-data
3. Optionally posts the converted resources to the FHIR server
4. Displays conversion results and statistics

Requirements:
- FHIR_URL must be set (or passed via --fhir-url)
- User/application identity must have FHIR Data Contributor role
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Import sample data
sys.path.insert(0, str(Path(__file__).parent))
from sample_hl7v2_data import get_all_messages, get_patient_messages


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert and load HL7v2 sample data using $convert-data operation."
    )
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("FHIR_URL"),
        help="Azure FHIR service URL",
    )
    parser.add_argument(
        "--patient-id",
        choices=["PAT001", "PAT002", "all"],
        default="all",
        help="Which patient's data to convert (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Convert but don't POST resources to FHIR server",
    )
    parser.add_argument(
        "--template-collection",
        default="microsofthealth/fhirconverter:default",
        help="Template collection reference (default: microsofthealth/fhirconverter:default)",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional directory to save converted FHIR resources as JSON files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Display detailed conversion output",
    )
    return parser.parse_args()


def validate_inputs(args):
    """Validate required inputs."""
    if not args.fhir_url:
        sys.exit("Missing FHIR service URL. Set FHIR_URL or pass --fhir-url.")
    return args.fhir_url.rstrip("/")


def convert_hl7v2_message(
    credential,
    fhir_url,
    message_content,
    template,
    template_collection,
):
    """
    Convert a single HL7v2 message using $convert-data.

    Args:
        credential: Azure credential for authentication
        fhir_url: FHIR service URL
        message_content: HL7v2 message content
        template: Root template name (e.g., "ADT_A01")
        template_collection: Template collection reference

    Returns:
        dict: Converted FHIR Bundle or None if error
    """
    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Build Parameters resource for $convert-data
    payload = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "inputData", "valueString": message_content},
            {"name": "inputDataType", "valueString": "Hl7v2"},
            {"name": "templateCollectionReference", "valueString": template_collection},
            {"name": "rootTemplate", "valueString": template},
        ],
    }

    try:
        response = requests.post(
            f"{fhir_url}/$convert-data",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"  ✗ Conversion failed: {response.status_code}")
            print(f"    {response.text}")
            return None

    except Exception as e:
        print(f"  ✗ Error during conversion: {e}")
        return None


def post_resource_to_fhir(credential, fhir_url, resource, patient_id_map=None):
    """
    POST a single FHIR resource to the server with conditional create for Patients.

    Args:
        credential: Azure credential for authentication
        fhir_url: FHIR service URL
        resource: FHIR resource to POST
        patient_id_map: Optional dict mapping temporary patient IDs to actual server IDs

    Returns:
        tuple: (success: bool, resource_id: str)
    """
    resource_type = resource.get("resourceType")
    if not resource_type:
        print("  ✗ Invalid resource: missing resourceType")
        return False, "missing resourceType"

    # Update patient references before posting
    if patient_id_map:
        resource = update_patient_references(resource, patient_id_map)

    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/fhir+json",
    }

    # For Patient resources, use conditional create based on identifier
    if resource_type == "Patient":
        # Find the MRN identifier
        identifiers = resource.get("identifier", [])
        mrn_identifier = None
        for identifier in identifiers:
            if "MRN" in identifier.get("system", ""):
                mrn_identifier = identifier.get("value")
                break

        if mrn_identifier:
            # Use conditional create: only create if no patient with this identifier exists
            headers["If-None-Exist"] = f"identifier={mrn_identifier}"

    try:
        response = requests.post(
            f"{fhir_url}/{resource_type}",
            headers=headers,
            json=resource,
            timeout=30,
        )

        if response.status_code in [200, 201]:
            created = response.json()
            resource_id = created.get("id", "unknown")
            return True, resource_id
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"

    except Exception as e:
        return False, str(e)


def update_patient_references(resource, patient_id_map):
    """
    Update Patient references in a resource using the patient ID mapping.

    Args:
        resource: FHIR resource (will be modified in place)
        patient_id_map: Dict mapping temporary patient IDs to actual server IDs

    Returns:
        Updated resource
    """
    # Convert to JSON string to do bulk replacements
    resource_str = json.dumps(resource)

    # Replace all patient ID references
    for temp_id, actual_id in patient_id_map.items():
        # Replace references like "Patient/temp-id"
        resource_str = resource_str.replace(f"Patient/{temp_id}", f"Patient/{actual_id}")

    return json.loads(resource_str)


def extract_resources_from_bundle(bundle):
    """
    Extract individual resources from a FHIR Bundle.

    Args:
        bundle: FHIR Bundle resource

    Returns:
        list: List of FHIR resources
    """
    if bundle.get("resourceType") != "Bundle":
        return [bundle]

    resources = []
    for entry in bundle.get("entry", []):
        if "resource" in entry:
            resources.append(entry["resource"])

    return resources


def save_resource_to_file(resource, output_dir, filename):
    """Save a FHIR resource to a JSON file."""
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(resource, f, indent=2)

    print(f"  → Saved to {output_path}")


def process_messages(
    credential,
    fhir_url,
    messages,
    template_collection,
    dry_run,
    output_dir,
    verbose,
):
    """
    Process all messages: convert and optionally load to FHIR server.

    Returns:
        dict: Statistics about the conversion and loading process
    """
    stats = {
        "total_messages": len(messages),
        "converted": 0,
        "conversion_failed": 0,
        "resources_created": 0,
        "resources_failed": 0,
        "resource_types": {},
    }

    # Track patient ID mappings across all messages
    # Maps temporary patient IDs (from converter) to actual server patient IDs
    patient_id_map = {}

    for idx, (patient_id, msg_type, template, content) in enumerate(messages, 1):
        print(f"\n[{idx}/{len(messages)}] Processing {patient_id} - {msg_type}")
        print(f"  Template: {template}")

        # Convert using $convert-data
        bundle = convert_hl7v2_message(
            credential, fhir_url, content, template, template_collection
        )

        if not bundle:
            stats["conversion_failed"] += 1
            continue

        stats["converted"] += 1

        if verbose:
            print(f"  ✓ Converted to FHIR Bundle")
            print(f"    Bundle type: {bundle.get('type', 'unknown')}")

        # Extract resources from bundle
        resources = extract_resources_from_bundle(bundle)
        print(f"  → Extracted {len(resources)} resource(s)")

        # Save to file if output directory specified
        if output_dir:
            filename = f"{patient_id}_{template}_{idx}.json"
            save_resource_to_file(bundle, output_dir, filename)

        # Track resource types
        for resource in resources:
            resource_type = resource.get("resourceType", "Unknown")
            stats["resource_types"][resource_type] = (
                stats["resource_types"].get(resource_type, 0) + 1
            )

        # POST resources to FHIR server (unless dry-run)
        if not dry_run:
            print(f"  → Posting resources to FHIR server...")

            # Separate Patient resources from others
            patient_resources = [r for r in resources if r.get("resourceType") == "Patient"]
            other_resources = [r for r in resources if r.get("resourceType") != "Patient"]

            # Post Patient resources first with conditional create
            for resource in patient_resources:
                temp_patient_id = resource.get("id")
                success, result = post_resource_to_fhir(
                    credential, fhir_url, resource, patient_id_map
                )

                if success:
                    stats["resources_created"] += 1
                    # Map temporary patient ID to actual server ID
                    if temp_patient_id and result != "unknown":
                        patient_id_map[temp_patient_id] = result
                    if verbose:
                        print(f"    ✓ Patient/{result} (conditional create)")
                else:
                    stats["resources_failed"] += 1
                    print(f"    ✗ Failed to create Patient: {result}")

            # Post other resources with updated patient references
            for resource in other_resources:
                resource_type = resource.get("resourceType")
                success, result = post_resource_to_fhir(
                    credential, fhir_url, resource, patient_id_map
                )

                if success:
                    stats["resources_created"] += 1
                    if verbose:
                        print(f"    ✓ Created {resource_type}/{result}")
                else:
                    stats["resources_failed"] += 1
                    print(f"    ✗ Failed to create {resource_type}: {result}")
        else:
            print(f"  → Dry-run mode: skipping FHIR server POST")

    return stats


def print_summary(stats, dry_run):
    """Print summary statistics."""
    print("\n" + "=" * 80)
    print("CONVERSION SUMMARY")
    print("=" * 80)
    print(f"Total messages processed:    {stats['total_messages']}")
    print(f"Successfully converted:      {stats['converted']}")
    print(f"Conversion failures:         {stats['conversion_failed']}")

    if stats["resource_types"]:
        print(f"\nResource types converted:")
        for resource_type, count in sorted(stats["resource_types"].items()):
            print(f"  - {resource_type}: {count}")

    if not dry_run:
        print(f"\nFHIR Server Upload:")
        print(f"  Resources created:         {stats['resources_created']}")
        print(f"  Upload failures:           {stats['resources_failed']}")
    else:
        print(f"\nDry-run mode: Resources not uploaded to FHIR server")

    print("=" * 80)


def main():
    load_dotenv()
    args = parse_args()
    fhir_url = validate_inputs(args)

    print("=" * 80)
    print("HL7v2 to FHIR Conversion using $convert-data")
    print("=" * 80)
    print(f"FHIR Server: {fhir_url}")
    print(f"Template Collection: {args.template_collection}")
    print(f"Mode: {'Dry-run (no POST)' if args.dry_run else 'Convert and POST'}")
    if args.output_dir:
        print(f"Output Directory: {args.output_dir}")
    print("=" * 80)

    # Get messages to process
    if args.patient_id == "all":
        messages = get_all_messages()
    else:
        messages = get_patient_messages(args.patient_id)

    if not messages:
        sys.exit(f"No messages found for patient {args.patient_id}")

    print(f"\nFound {len(messages)} HL7v2 message(s) to convert")

    # Authenticate
    print("\nAuthenticating with Azure...")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    # Process messages
    stats = process_messages(
        credential,
        fhir_url,
        messages,
        args.template_collection,
        args.dry_run,
        args.output_dir,
        args.verbose,
    )

    # Print summary
    print_summary(stats, args.dry_run)

    # Exit with error if any failures
    if stats["conversion_failed"] > 0 or stats["resources_failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
