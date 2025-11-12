#!/usr/bin/env python3
"""
Query and view data from Azure FHIR service.
"""

import argparse
import json
import os
import sys

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


def parse_args():
    parser = argparse.ArgumentParser(description="Query Azure FHIR service")
    parser.add_argument(
        "--resource-type",
        default="Patient",
        help="FHIR resource type to query (e.g., Patient, Observation, Condition)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of resources to return (default: 10)",
    )
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("FHIR_URL"),
        help="Azure FHIR service URL",
    )
    parser.add_argument(
        "--search",
        help="Additional search parameters (e.g., 'name=Smith&birthdate=gt2000-01-01')",
    )
    return parser.parse_args()


def query_fhir(fhir_url: str, credential: DefaultAzureCredential, resource_type: str, count: int, search: str = None):
    """Query FHIR service and return results."""
    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    }

    # Build query URL
    query_url = f"{fhir_url}/{resource_type}?_count={count}"
    if search:
        query_url += f"&{search}"

    response = requests.get(query_url, headers=headers, timeout=30)

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        sys.exit(1)

    return response.json()


def get_resource_count(fhir_url: str, credential: DefaultAzureCredential, resource_type: str):
    """Get total count of resources."""
    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    }

    query_url = f"{fhir_url}/{resource_type}?_summary=count"
    response = requests.get(query_url, headers=headers, timeout=30)

    if response.status_code == 200:
        data = response.json()
        return data.get('total', 0)
    return None


def display_results(bundle: dict, resource_type: str):
    """Display query results in a readable format."""
    total = bundle.get('total', 0)
    entries = bundle.get('entry', [])

    print("\n" + "=" * 70)
    print(f"Query Results: {resource_type}")
    print("=" * 70)
    print(f"Total available: {total}")
    print(f"Returned: {len(entries)}")
    print("=" * 70)

    if not entries:
        print("\nNo resources found.")
        return

    for idx, entry in enumerate(entries, 1):
        resource = entry.get('resource', {})
        resource_id = resource.get('id', 'N/A')

        print(f"\n[{idx}] {resource_type}/{resource_id}")
        print("-" * 70)

        # Display key fields based on resource type
        if resource_type == "Patient":
            name = resource.get('name', [{}])[0]
            given = ' '.join(name.get('given', []))
            family = name.get('family', '')
            full_name = f"{given} {family}".strip()

            gender = resource.get('gender', 'N/A')
            birth_date = resource.get('birthDate', 'N/A')

            print(f"Name: {full_name}")
            print(f"Gender: {gender}")
            print(f"Birth Date: {birth_date}")

        elif resource_type == "Observation":
            code = resource.get('code', {}).get('coding', [{}])[0]
            code_display = code.get('display', 'N/A')

            value = resource.get('valueQuantity', {})
            value_str = f"{value.get('value', 'N/A')} {value.get('unit', '')}".strip()

            effective = resource.get('effectiveDateTime', 'N/A')

            print(f"Code: {code_display}")
            print(f"Value: {value_str}")
            print(f"Date: {effective}")

        elif resource_type == "Condition":
            code = resource.get('code', {}).get('coding', [{}])[0]
            code_display = code.get('display', 'N/A')

            onset = resource.get('onsetDateTime', 'N/A')
            clinical_status = resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code', 'N/A')

            print(f"Condition: {code_display}")
            print(f"Onset: {onset}")
            print(f"Status: {clinical_status}")

        elif resource_type == "Encounter":
            enc_class = resource.get('class', {}).get('code', 'N/A')
            period = resource.get('period', {})
            start = period.get('start', 'N/A')

            print(f"Class: {enc_class}")
            print(f"Start: {start}")

        else:
            # Generic display for other resource types
            print(json.dumps(resource, indent=2)[:500] + "...")


def main():
    load_dotenv()
    args = parse_args()

    if not args.fhir_url:
        sys.exit("Missing FHIR service URL. Set FHIR_URL or pass --fhir-url.")

    fhir_url = args.fhir_url.rstrip("/")

    print(f"Connecting to: {fhir_url}")
    print(f"Resource type: {args.resource_type}")

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    # Get total count
    print("\nFetching resource count...")
    total_count = get_resource_count(fhir_url, credential, args.resource_type)
    if total_count is not None:
        print(f"Total {args.resource_type} resources: {total_count}")

    # Query resources
    print(f"\nQuerying {args.count} resources...")
    bundle = query_fhir(fhir_url, credential, args.resource_type, args.count, args.search)

    # Display results
    display_results(bundle, args.resource_type)

    print("\n" + "=" * 70)
    print("Query complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
