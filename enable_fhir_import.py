#!/usr/bin/env python3
"""
Enable bulk import on Azure FHIR service using Azure REST API.

This script configures the FHIR service to enable the $import operation
required for bulk data ingestion, enables system-assigned managed identity,
and assigns Storage Blob Data Contributor role to the identity.
"""

import os
import sys
import json
import uuid
import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential


def get_subscription_id():
    """Extract subscription ID from environment or Azure CLI default."""
    import subprocess
    result = subprocess.run(
        ["az", "account", "show", "--query", "id", "-o", "tsv"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def assign_storage_role(subscription_id, storage_account_name, storage_resource_group, principal_id, headers):
    """Assign Storage Blob Data Contributor role to the managed identity."""
    # Storage Blob Data Contributor role ID
    role_definition_id = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"

    # Construct storage account resource ID
    storage_resource_id = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{storage_resource_group}"
        f"/providers/Microsoft.Storage/storageAccounts/{storage_account_name}"
    )

    # Construct role assignment URL
    api_version = "2022-04-01"
    role_assignment_name = str(uuid.uuid4())
    role_assignment_url = (
        f"https://management.azure.com{storage_resource_id}"
        f"/providers/Microsoft.Authorization/roleAssignments/{role_assignment_name}"
        f"?api-version={api_version}"
    )

    # Role assignment payload
    role_payload = {
        "properties": {
            "roleDefinitionId": f"{storage_resource_id}/providers/Microsoft.Authorization/roleDefinitions/{role_definition_id}",
            "principalId": principal_id,
            "principalType": "ServicePrincipal"
        }
    }

    print(f"\nAssigning Storage Blob Data Contributor role...")
    print(f"  Storage Account: {storage_account_name}")
    print(f"  Principal ID: {principal_id}")

    response = requests.put(role_assignment_url, headers=headers, json=role_payload, timeout=30)

    if response.status_code in [200, 201]:
        print(f"✓ Role assignment successful")
        return True
    elif response.status_code == 409:
        # Role assignment already exists
        print(f"✓ Role assignment already exists")
        return True
    else:
        print(f"✗ Role assignment failed (HTTP {response.status_code})")
        print(response.text)
        return False


def main():
    # Load environment variables
    load_dotenv()

    resource_group = os.getenv("FHIR_RESOURCE_GROUP")
    workspace_name = os.getenv("FHIR_WORKSPACE_NAME")
    service_name = os.getenv("FHIR_SERVICE_NAME")
    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME")
    storage_resource_group = os.getenv("STORAGE_RESOURCE_GROUP")

    # If storage account name is not provided, try to extract from SAS URL
    if not storage_account_name:
        sas_url = os.getenv("FHIR_IMPORT_CONTAINER_SAS_URL", "")
        if "blob.core.windows.net" in sas_url:
            # Extract storage account name from URL like https://account.blob.core.windows.net/...
            storage_account_name = sas_url.split("//")[1].split(".")[0]
            print(f"Extracted storage account name from SAS URL: {storage_account_name}")

    # Use FHIR resource group as default for storage if not specified
    if not storage_resource_group:
        storage_resource_group = resource_group

    if not all([resource_group, workspace_name, service_name]):
        print("Error: Missing required environment variables:")
        print(f"  FHIR_RESOURCE_GROUP: {resource_group}")
        print(f"  FHIR_WORKSPACE_NAME: {workspace_name}")
        print(f"  FHIR_SERVICE_NAME: {service_name}")
        sys.exit(1)

    if not storage_account_name:
        print("Warning: Storage account name not found. Skipping RBAC role assignment.")
        print("  Set STORAGE_ACCOUNT_NAME or FHIR_IMPORT_CONTAINER_SAS_URL to enable role assignment.")
        assign_rbac = False
    else:
        assign_rbac = True

    print("=" * 70)
    print("Azure FHIR Service - Enable Bulk Import")
    print("=" * 70)
    print(f"Resource Group: {resource_group}")
    print(f"Workspace Name: {workspace_name}")
    print(f"Service Name: {service_name}")
    if assign_rbac:
        print(f"Storage Account: {storage_account_name}")
        print(f"Storage Resource Group: {storage_resource_group}")
    print("=" * 70)

    # Get subscription ID
    subscription_id = get_subscription_id()
    if not subscription_id:
        print("\nError: Could not determine subscription ID. Run 'az login' first.")
        sys.exit(1)

    print(f"\nSubscription ID: {subscription_id}")

    # Authenticate
    try:
        print("\nAuthenticating...")
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

        # Get access token for Azure Resource Manager
        token = credential.get_token("https://management.azure.com/.default")
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json"
        }

        # Construct the resource URL
        api_version = "2024-03-31"
        base_url = f"https://management.azure.com/subscriptions/{subscription_id}"
        resource_url = (
            f"{base_url}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.HealthcareApis/workspaces/{workspace_name}"
            f"/fhirservices/{service_name}"
        )

        # Get current configuration
        print("\nRetrieving current FHIR service configuration...")
        get_url = f"{resource_url}?api-version={api_version}"
        response = requests.get(get_url, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"Error getting FHIR service: {response.status_code}")
            print(response.text)
            sys.exit(1)

        current_config = response.json()
        print(f"Current configuration:")
        print(f"  Location: {current_config.get('location')}")
        print(f"  Kind: {current_config.get('kind')}")

        # Check provisioning state
        provisioning_state = current_config.get('properties', {}).get('provisioningState', 'Unknown')
        print(f"  Provisioning State: {provisioning_state}")

        # Wait for provisioning to complete if needed
        if provisioning_state not in ['Succeeded', 'Failed']:
            print(f"\nWaiting for provisioning to complete (current state: {provisioning_state})...")
            import time
            max_wait = 300  # 5 minutes
            waited = 0
            while provisioning_state not in ['Succeeded', 'Failed'] and waited < max_wait:
                time.sleep(10)
                waited += 10
                response = requests.get(get_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    current_config = response.json()
                    provisioning_state = current_config.get('properties', {}).get('provisioningState', 'Unknown')
                    print(f"  State after {waited}s: {provisioning_state}")

            if provisioning_state != 'Succeeded':
                print(f"\nError: Provisioning did not complete successfully (state: {provisioning_state})")
                sys.exit(1)
            print("Provisioning completed successfully!")

        import_config = current_config.get('properties', {}).get('importConfiguration', {})
        print(f"  Import Enabled: {import_config.get('enabled', False)}")
        print(f"  Initial Import Mode: {import_config.get('initialImportMode', False)}")

        # Check identity
        identity = current_config.get('identity', {})
        print(f"  Identity Type: {identity.get('type', 'None')}")

        # Enable import using az resource update (the REST API PATCH doesn't work reliably)
        print("\n" + "=" * 70)
        print("Enabling system-assigned managed identity and bulk import...")
        print("=" * 70)

        print("Using Azure CLI to update FHIR service configuration...")
        import subprocess

        # First ensure managed identity is enabled
        if identity.get('type') != 'SystemAssigned':
            print("Enabling system-assigned managed identity...")
            identity_cmd = [
                "az", "resource", "update",
                "--ids", f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.HealthcareApis/workspaces/{workspace_name}/fhirservices/{service_name}",
                "--api-version", "2022-06-01",
                "--set", "identity.type=SystemAssigned"
            ]
            result = subprocess.run(identity_cmd, capture_output=True, text=True, timeout=180)
            if result.returncode != 0:
                print(f"Error enabling managed identity: {result.stderr}")
                sys.exit(1)
            print("✓ Managed identity enabled")

        # Enable import configuration with integration data store
        print(f"Enabling import configuration with integration data store: {storage_account_name}")
        print("Note: Initial import mode is required for importing data into an empty FHIR server")
        import_cmd = [
            "az", "resource", "update",
            "--ids", f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.HealthcareApis/workspaces/{workspace_name}/fhirservices/{service_name}",
            "--api-version", "2022-06-01",
            "--set",
            "properties.importConfiguration.enabled=true",
            "properties.importConfiguration.initialImportMode=true",
            f"properties.importConfiguration.integrationDataStore={storage_account_name}"
        ]

        result = subprocess.run(import_cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            print(f"\n" + "=" * 70)
            print(f"ERROR: Failed to enable bulk import")
            print("=" * 70)
            print(result.stderr)
            sys.exit(1)

        # Parse the JSON output
        result_data = json.loads(result.stdout)

        print("\n" + "=" * 70)
        print("SUCCESS! Configuration updated")
        print("=" * 70)

        identity_result = result_data.get('identity', {})
        print(f"\nManaged Identity:")
        print(f"  Type: {identity_result.get('type', 'None')}")
        principal_id = identity_result.get('principalId', 'N/A')
        print(f"  Principal ID: {principal_id}")

        import_result = result_data.get('properties', {}).get('importConfiguration', {})
        print(f"\nImport Configuration:")
        print(f"  Enabled: {import_result.get('enabled', False)}")
        print(f"  Initial Import Mode: {import_result.get('initialImportMode', False)}")
        print(f"  Integration Data Store: {import_result.get('integrationDataStore', 'N/A')}")

        # Assign Storage Blob Data Contributor role
        if assign_rbac and principal_id != 'N/A':
            print("\n" + "=" * 70)
            print("Assigning Storage RBAC Role")
            print("=" * 70)
            role_assigned = assign_storage_role(
                subscription_id,
                storage_account_name,
                storage_resource_group,
                principal_id,
                headers
            )
            if not role_assigned:
                print("\n⚠ Warning: Failed to assign storage role. You may need to assign it manually.")
                print(f"  Role: Storage Blob Data Contributor")
                print(f"  Principal ID: {principal_id}")
                print(f"  Storage Account: {storage_account_name}")

        print("\n" + "=" * 70)
        print("Next Steps")
        print("=" * 70)
        print("\nYou can now run the load_synthea_data.py script to import data:")
        print(f"  python load_synthea_data.py --input-dir synthea/ils_miami --skip-upload --prefix synthea-20251112212922 --wait")

    except Exception as e:
        print(f"\n" + "=" * 70)
        print("ERROR: Unexpected error")
        print("=" * 70)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
