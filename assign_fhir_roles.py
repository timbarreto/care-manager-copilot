#!/usr/bin/env python3
"""
Assign FHIR Data Contributor role to enable data uploads.
"""

import os
import subprocess
import sys
from dotenv import load_dotenv


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def main():
    load_dotenv()

    resource_group = os.getenv("FHIR_RESOURCE_GROUP")
    workspace_name = os.getenv("FHIR_WORKSPACE_NAME")
    service_name = os.getenv("FHIR_SERVICE_NAME")

    if not all([resource_group, workspace_name, service_name]):
        print("Error: Missing required environment variables")
        sys.exit(1)

    print("=" * 70)
    print("Azure FHIR Service - Assign Roles")
    print("=" * 70)

    # Get current user
    returncode, user_id, stderr = run_command([
        "az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"
    ])

    if returncode != 0:
        print(f"Error getting current user: {stderr}")
        sys.exit(1)

    print(f"Current user ID: {user_id}")

    # Get subscription ID
    returncode, subscription_id, _ = run_command([
        "az", "account", "show", "--query", "id", "-o", "tsv"
    ])

    # Construct FHIR service resource ID
    fhir_resource_id = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.HealthcareApis/workspaces/{workspace_name}"
        f"/fhirservices/{service_name}"
    )

    print(f"FHIR Resource ID: {fhir_resource_id}")

    # Assign FHIR Data Contributor role
    print("\nAssigning 'FHIR Data Contributor' role...")

    returncode, output, stderr = run_command([
        "az", "role", "assignment", "create",
        "--role", "FHIR Data Contributor",
        "--assignee", user_id,
        "--scope", fhir_resource_id
    ])

    if returncode == 0:
        print("\n" + "=" * 70)
        print("SUCCESS! Role assigned")
        print("=" * 70)
        print("\nYou can now run the batch upload script:")
        print("  python load_synthea_data_batch.py --input-dir synthea/ils_miami")
    else:
        if "already exists" in stderr.lower():
            print("\n" + "=" * 70)
            print("Role already assigned!")
            print("=" * 70)
        else:
            print(f"\nError: {stderr}")
            sys.exit(1)


if __name__ == "__main__":
    main()
