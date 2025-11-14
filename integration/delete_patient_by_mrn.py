#!/usr/bin/env python3
"""
Delete patient and all associated FHIR data by MRN.

This script:
1. Finds all Patient resources with the given MRN identifier
2. Finds all related clinical resources (Observations, Encounters, etc.)
3. Deletes all related resources first
4. Deletes the Patient resources last

Usage:
    python delete_patient_by_mrn.py --mrn PAT001
    python delete_patient_by_mrn.py --mrn PAT001 --dry-run
"""

import argparse
import os
import sys
from typing import List, Dict, Any

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Delete patient and all associated FHIR data by MRN."
    )
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("FHIR_URL"),
        help="Azure FHIR service URL",
    )
    parser.add_argument(
        "--mrn",
        required=True,
        help="Patient MRN identifier to delete",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    return parser.parse_args()


def validate_inputs(args):
    """Validate required inputs."""
    if not args.fhir_url:
        sys.exit("Missing FHIR service URL. Set FHIR_URL or pass --fhir-url.")
    return args.fhir_url.rstrip("/")


def find_patients_by_mrn(fhir_url: str, token: str, mrn: str) -> List[Dict[str, Any]]:
    """
    Find all Patient resources with the given MRN.

    Args:
        fhir_url: FHIR service URL
        token: Bearer token for authentication
        mrn: Patient MRN identifier

    Returns:
        List of Patient resources
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/fhir+json"
    }

    response = requests.get(
        f"{fhir_url}/Patient?identifier={mrn}",
        headers=headers,
        timeout=30
    )
    response.raise_for_status()

    bundle = response.json()
    patients = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            patients.append(resource)

    return patients


def find_related_resources(
    fhir_url: str,
    token: str,
    patient_ids: List[str]
) -> Dict[str, List[str]]:
    """
    Find all resources related to the given patient IDs.

    Args:
        fhir_url: FHIR service URL
        token: Bearer token for authentication
        patient_ids: List of Patient resource IDs

    Returns:
        Dictionary mapping resource type to list of resource IDs
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/fhir+json"
    }

    # Resource types that typically reference patients
    resource_types = [
        "Observation",
        "Condition",
        "MedicationRequest",
        "Encounter",
        "CarePlan",
        "Procedure",
        "DiagnosticReport",
        "AllergyIntolerance",
        "Immunization",
        "ServiceRequest",
        "Specimen",
        "DocumentReference",
        "MessageHeader",
        "Provenance",
        "Practitioner",
        "PractitionerRole",
        "Organization",
        "Location",
    ]

    related_resources = {}

    for resource_type in resource_types:
        try:
            # For resource types that reference patients via 'subject'
            if resource_type in ["Observation", "Condition", "MedicationRequest",
                                "CarePlan", "Procedure", "DiagnosticReport",
                                "AllergyIntolerance", "Immunization", "ServiceRequest",
                                "DocumentReference"]:
                patient_refs = ",".join([f"Patient/{pid}" for pid in patient_ids])
                url = f"{fhir_url}/{resource_type}?subject={patient_refs}&_count=1000"
            # For Encounter which uses 'subject'
            elif resource_type == "Encounter":
                patient_refs = ",".join([f"Patient/{pid}" for pid in patient_ids])
                url = f"{fhir_url}/{resource_type}?subject={patient_refs}&_count=1000"
            # For Specimen which uses 'subject'
            elif resource_type == "Specimen":
                patient_refs = ",".join([f"Patient/{pid}" for pid in patient_ids])
                url = f"{fhir_url}/{resource_type}?subject={patient_refs}&_count=1000"
            else:
                # For other resources, just get recent ones that might be related
                # This is a broader sweep to catch MessageHeader, Provenance, etc.
                url = f"{fhir_url}/{resource_type}?_count=1000&_sort=-_lastUpdated"

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            bundle = response.json()

            resource_ids = []
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                resource_id = resource.get("id")

                # For non-patient-specific queries, verify the resource is actually related
                if resource_type not in ["Observation", "Condition", "MedicationRequest",
                                        "CarePlan", "Procedure", "DiagnosticReport",
                                        "AllergyIntolerance", "Immunization", "ServiceRequest",
                                        "Encounter", "Specimen", "DocumentReference"]:
                    # Check if resource references any of our patient IDs
                    resource_str = str(resource)
                    if not any(f"Patient/{pid}" in resource_str for pid in patient_ids):
                        continue

                if resource_id:
                    resource_ids.append(resource_id)

            if resource_ids:
                related_resources[resource_type] = resource_ids

        except Exception as e:
            # If a resource type query fails, continue with others
            print(f"  Warning: Failed to query {resource_type}: {e}")

    return related_resources


def delete_resource(fhir_url: str, token: str, resource_type: str, resource_id: str) -> bool:
    """
    Delete a single FHIR resource.

    Args:
        fhir_url: FHIR service URL
        token: Bearer token for authentication
        resource_type: Type of resource (e.g., "Observation")
        resource_id: Resource ID

    Returns:
        True if successful, False otherwise
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/fhir+json"
    }

    try:
        response = requests.delete(
            f"{fhir_url}/{resource_type}/{resource_id}",
            headers=headers,
            timeout=30
        )

        # 200, 204, or 404 are all acceptable for delete
        # (404 means already deleted)
        if response.status_code in [200, 204, 404]:
            return True
        else:
            print(f"    ✗ Failed to delete {resource_type}/{resource_id}: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"    ✗ Error deleting {resource_type}/{resource_id}: {e}")
        return False


def main():
    load_dotenv()
    args = parse_args()
    fhir_url = validate_inputs(args)

    print("=" * 80)
    print("Delete Patient and Associated FHIR Data by MRN")
    print("=" * 80)
    print(f"FHIR Server: {fhir_url}")
    print(f"MRN: {args.mrn}")
    print(f"Mode: {'DRY RUN (no deletions)' if args.dry_run else 'DELETE (will remove data)'}")
    print("=" * 80)

    # Authenticate
    print("\nAuthenticating with Azure...")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    token = credential.get_token(f"{fhir_url}/.default").token

    # Find patients
    print(f"\nSearching for patients with MRN '{args.mrn}'...")
    patients = find_patients_by_mrn(fhir_url, token, args.mrn)

    if not patients:
        print(f"No patients found with MRN '{args.mrn}'")
        return

    print(f"Found {len(patients)} patient(s):")
    patient_ids = []
    for patient in patients:
        patient_id = patient["id"]
        patient_ids.append(patient_id)
        name = patient.get("name", [{}])[0]
        full_name = f"{' '.join(name.get('given', []))} {name.get('family', '')}"
        print(f"  - Patient/{patient_id}: {full_name} (DOB: {patient.get('birthDate', 'N/A')})")

    # Find related resources
    print(f"\nSearching for related resources...")
    related_resources = find_related_resources(fhir_url, token, patient_ids)

    total_related = sum(len(ids) for ids in related_resources.values())
    print(f"Found {total_related} related resource(s):")
    for resource_type, resource_ids in sorted(related_resources.items()):
        print(f"  - {resource_type}: {len(resource_ids)}")

    # Summary
    total_deletions = len(patients) + total_related
    print(f"\nTotal resources to delete: {total_deletions}")
    print(f"  - Patients: {len(patients)}")
    print(f"  - Related resources: {total_related}")

    if args.dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN MODE - No resources were deleted")
        print("=" * 80)
        return

    # Confirm deletion
    print("\n" + "=" * 80)
    print("WARNING: This will permanently delete all the above resources!")
    print("=" * 80)
    response = input("Type 'DELETE' to confirm: ")

    if response != "DELETE":
        print("Deletion cancelled.")
        return

    # Delete related resources first
    print("\nDeleting related resources...")
    deleted_count = 0
    failed_count = 0

    for resource_type, resource_ids in sorted(related_resources.items()):
        print(f"\n  Deleting {len(resource_ids)} {resource_type} resource(s)...")
        for resource_id in resource_ids:
            if delete_resource(fhir_url, token, resource_type, resource_id):
                deleted_count += 1
            else:
                failed_count += 1

    # Delete patients last
    print(f"\n  Deleting {len(patients)} Patient resource(s)...")
    for patient in patients:
        patient_id = patient["id"]
        if delete_resource(fhir_url, token, "Patient", patient_id):
            deleted_count += 1
        else:
            failed_count += 1

    # Summary
    print("\n" + "=" * 80)
    print("DELETION SUMMARY")
    print("=" * 80)
    print(f"Successfully deleted: {deleted_count}")
    print(f"Failed to delete:     {failed_count}")
    print("=" * 80)

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
