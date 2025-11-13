#!/usr/bin/env python3
"""
Disable initial import mode on Azure FHIR service.

Initial import mode locks the FHIR service to only allow bulk $import operations.
This script disables initial import mode to allow:
- Normal FHIR CRUD operations (POST, PUT, DELETE)
- $convert-data operations
- Regular client access

While keeping bulk import enabled for future use.
"""

import os
import sys
import json
import subprocess
from dotenv import load_dotenv


def get_subscription_id():
    """Extract subscription ID from Azure CLI."""
    result = subprocess.run(
        ["az", "account", "show", "--query", "id", "-o", "tsv"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_current_config(subscription_id, resource_group, workspace_name, service_name):
    """Get current FHIR service configuration."""
    resource_id = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.HealthcareApis/workspaces/{workspace_name}"
        f"/fhirservices/{service_name}"
    )

    result = subprocess.run(
        [
            "az", "resource", "show",
            "--ids", resource_id,
            "--api-version", "2022-06-01"
        ],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        print(f"Error getting current configuration: {result.stderr}")
        sys.exit(1)


def disable_initial_import_mode(subscription_id, resource_group, workspace_name, service_name):
    """Disable initial import mode while keeping import enabled."""
    resource_id = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.HealthcareApis/workspaces/{workspace_name}"
        f"/fhirservices/{service_name}"
    )

    print("Disabling initial import mode...")
    print(f"  Resource: {resource_id}")

    result = subprocess.run(
        [
            "az", "resource", "update",
            "--ids", resource_id,
            "--api-version", "2022-06-01",
            "--set", "properties.importConfiguration.initialImportMode=false"
        ],
        capture_output=True,
        text=True,
        timeout=600
    )

    if result.returncode != 0:
        print(f"\n{'=' * 70}")
        print(f"ERROR: Failed to disable initial import mode")
        print("=" * 70)
        print(result.stderr)
        sys.exit(1)

    return json.loads(result.stdout)


def main():
    # Load environment variables
    load_dotenv()

    resource_group = os.getenv("FHIR_RESOURCE_GROUP")
    workspace_name = os.getenv("FHIR_WORKSPACE_NAME")
    service_name = os.getenv("FHIR_SERVICE_NAME")

    if not all([resource_group, workspace_name, service_name]):
        print("Error: Missing required environment variables:")
        print(f"  FHIR_RESOURCE_GROUP: {resource_group}")
        print(f"  FHIR_WORKSPACE_NAME: {workspace_name}")
        print(f"  FHIR_SERVICE_NAME: {service_name}")
        sys.exit(1)

    print("=" * 70)
    print("Azure FHIR Service - Disable Initial Import Mode")
    print("=" * 70)
    print(f"Resource Group: {resource_group}")
    print(f"Workspace Name: {workspace_name}")
    print(f"Service Name: {service_name}")
    print("=" * 70)

    # Get subscription ID
    subscription_id = get_subscription_id()
    if not subscription_id:
        print("\nError: Could not determine subscription ID. Run 'az login' first.")
        sys.exit(1)

    print(f"\nSubscription ID: {subscription_id}")

    # Get current configuration
    print("\nRetrieving current FHIR service configuration...")
    current_config = get_current_config(subscription_id, resource_group, workspace_name, service_name)

    import_config = current_config.get('properties', {}).get('importConfiguration', {})
    print(f"\nCurrent Import Configuration:")
    print(f"  Enabled: {import_config.get('enabled', False)}")
    print(f"  Initial Import Mode: {import_config.get('initialImportMode', False)}")
    print(f"  Integration Data Store: {import_config.get('integrationDataStore', 'N/A')}")

    # Check if already disabled
    if not import_config.get('initialImportMode', False):
        print("\n" + "=" * 70)
        print("Initial import mode is already disabled!")
        print("=" * 70)
        print("\nNo changes needed. The FHIR service is ready for:")
        print("  ✓ Normal FHIR operations (POST, PUT, DELETE)")
        print("  ✓ $convert-data operations")
        print("  ✓ Regular client access")
        print("  ✓ Bulk $import operations (import still enabled)")
        return

    # Disable initial import mode
    print("\n" + "=" * 70)
    print("Disabling Initial Import Mode")
    print("=" * 70)
    print("\nThis will:")
    print("  • Allow normal FHIR CRUD operations")
    print("  • Enable $convert-data operations")
    print("  • Keep bulk $import functionality enabled")
    print("  • Unlock the FHIR service for regular use")

    updated_config = disable_initial_import_mode(
        subscription_id, resource_group, workspace_name, service_name
    )

    # Verify the change
    updated_import_config = updated_config.get('properties', {}).get('importConfiguration', {})

    print("\n" + "=" * 70)
    print("SUCCESS! Configuration Updated")
    print("=" * 70)
    print(f"\nUpdated Import Configuration:")
    print(f"  Enabled: {updated_import_config.get('enabled', False)}")
    print(f"  Initial Import Mode: {updated_import_config.get('initialImportMode', False)}")
    print(f"  Integration Data Store: {updated_import_config.get('integrationDataStore', 'N/A')}")

    print("\n" + "=" * 70)
    print("FHIR Service is Now Ready")
    print("=" * 70)
    print("\nYou can now:")
    print("  ✓ Use normal FHIR operations (POST, PUT, PATCH, DELETE)")
    print("  ✓ Run $convert-data operations")
    print("  ✓ Access the service from client applications")
    print("  ✓ Still use $import for bulk data loading")

    print("\n" + "=" * 70)
    print("Next Steps")
    print("=" * 70)
    print("\nTest $convert-data operation:")
    print("  python integration/convert_and_load_hl7v2.py --dry-run")
    print("\nConvert and load HL7v2 sample data:")
    print("  python integration/convert_and_load_hl7v2.py")
    print("\nQuery FHIR data:")
    print("  python scripts/query_fhir_data.py --resource-type Patient --count 10")


if __name__ == "__main__":
    main()
