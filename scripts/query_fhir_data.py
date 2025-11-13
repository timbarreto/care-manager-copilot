#!/usr/bin/env python3
"""
Query and view data from Azure FHIR service.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


RESOURCE_DATE_PARAMS = {
    "Observation": "date",
    "Condition": "onset-date",
    "Encounter": "date",
    "Procedure": "performed",
    "MedicationRequest": "authoredon",
    "AllergyIntolerance": "recorded-date",
    "Immunization": "date",
    "DiagnosticReport": "date",
    "CarePlan": "date",
    "CareTeam": "date",
    "DocumentReference": "date",
    "Claim": "created",
    "ExplanationOfBenefit": "created",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Query Azure FHIR service")
    parser.add_argument(
        "--resource-type",
        default="Patient",
        help="FHIR resource type to query (e.g., Patient, Observation, Condition)",
    )
    parser.add_argument(
        "--patient-id",
        help="Patient ID to fetch all related data for",
    )
    parser.add_argument(
        "--years",
        type=int,
        help="Limit related resources to the last X years when using --patient-id.",
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


def get_patient(fhir_url: str, credential: DefaultAzureCredential, patient_id: str):
    """Get a specific patient by ID."""
    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    }

    query_url = f"{fhir_url}/Patient/{patient_id}"
    response = requests.get(query_url, headers=headers, timeout=30)

    if response.status_code != 200:
        print(f"Error fetching patient: {response.status_code}")
        print(response.text)
        sys.exit(1)

    return response.json()


def get_patient_resources(
    fhir_url: str,
    credential: DefaultAzureCredential,
    patient_id: str,
    resource_type: str,
    count: int = 1000,
    since: datetime | None = None,
):
    """Get all resources of a specific type for a patient."""
    access_token = credential.get_token(f"{fhir_url}/.default").token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    }

    patient_ref = patient_id if patient_id.startswith("Patient/") else f"Patient/{patient_id}"
    patient_id_only = patient_ref.split("/", 1)[1] if "/" in patient_ref else patient_ref

    search_params = [
        ("patient", patient_id_only),
        ("patient", patient_ref),
        ("subject", patient_id_only),
        ("subject", patient_ref),
    ]
    if resource_type in {"Claim", "ExplanationOfBenefit"}:
        search_params.extend(
            [("beneficiary", patient_id_only), ("beneficiary", patient_ref)]
        )

    combined_entries = []
    seen_resource_ids = set()

    date_filters = []
    if since:
        filter_param = RESOURCE_DATE_PARAMS.get(resource_type)
        if filter_param:
            filter_value = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            date_filters.append(f"{filter_param}=ge{filter_value}")

    for param, value in search_params:
        filter_str = "&".join(date_filters)
        filter_str = f"&{filter_str}" if filter_str else ""
        query_url = f"{fhir_url}/{resource_type}?{param}={value}{filter_str}&_count={count}"
        response = requests.get(query_url, headers=headers, timeout=30)
        if response.status_code != 200:
            continue
        bundle = response.json()
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            res_id = resource.get("id")
            if res_id and res_id in seen_resource_ids:
                continue
            if res_id:
                seen_resource_ids.add(res_id)
            combined_entries.append(entry)
        if len(combined_entries) >= count:
            break

    if not combined_entries:
        return None

    return {"resourceType": "Bundle", "entry": combined_entries}


def get_all_patient_data(
    fhir_url: str,
    credential: DefaultAzureCredential,
    patient_id: str,
    since: datetime | None = None,
):
    """Get patient and all related resources."""
    print(f"\nFetching all data for Patient/{patient_id}{f' since {since.date()}' if since else ''}...")

    # Get the patient
    patient = get_patient(fhir_url, credential, patient_id)

    # Define resource types to query
    resource_types = [
        "Observation",
        "Condition",
        "Encounter",
        "Procedure",
        "MedicationRequest",
        "AllergyIntolerance",
        "Immunization",
        "DiagnosticReport",
        "CarePlan",
        "CareTeam",
        "DocumentReference",
        "Claim",
        "ExplanationOfBenefit"
    ]

    all_data = {
        "patient": patient,
        "resources": {}
    }

    for resource_type in resource_types:
        print(f"  Fetching {resource_type}...")
        bundle = get_patient_resources(fhir_url, credential, patient_id, resource_type, since=since)
        if bundle and bundle.get('entry'):
            all_data['resources'][resource_type] = bundle.get('entry', [])
            print(f"    Found {len(bundle.get('entry', []))} {resource_type} resources")
        else:
            print(f"    No {resource_type} resources found")

    return all_data


def display_patient_data(patient_data: dict):
    """Display complete patient data with all related resources."""
    patient = patient_data['patient']
    resources = patient_data['resources']

    print("\n" + "=" * 80)
    print("COMPLETE PATIENT RECORD")
    print("=" * 80)

    # Display patient demographics
    patient_id = patient.get('id', 'N/A')
    name = patient.get('name', [{}])[0]
    given = ' '.join(name.get('given', []))
    family = name.get('family', '')
    full_name = f"{given} {family}".strip()
    gender = patient.get('gender', 'N/A')
    birth_date = patient.get('birthDate', 'N/A')

    print(f"\nPatient ID: {patient_id}")
    print(f"Name: {full_name}")
    print(f"Gender: {gender}")
    print(f"Birth Date: {birth_date}")

    # Display address if available
    if patient.get('address'):
        address = patient['address'][0]
        address_lines = address.get('line', [])
        city = address.get('city', '')
        state = address.get('state', '')
        postal = address.get('postalCode', '')
        print(f"Address: {', '.join(address_lines)}, {city}, {state} {postal}")

    # Display contact info
    if patient.get('telecom'):
        print("\nContact Information:")
        for telecom in patient['telecom']:
            system = telecom.get('system', 'N/A')
            value = telecom.get('value', 'N/A')
            print(f"  {system.capitalize()}: {value}")

    print("\n" + "-" * 80)
    print("RELATED RESOURCES")
    print("-" * 80)

    # Display summary of each resource type
    for resource_type, entries in resources.items():
        if entries:
            print(f"\n{resource_type}: {len(entries)} resources")
            print("-" * 40)

            # Display details for each resource
            for idx, entry in enumerate(entries[:5], 1):  # Show first 5 of each type
                resource = entry.get('resource', {})
                resource_id = resource.get('id', 'N/A')

                print(f"\n  [{idx}] {resource_type}/{resource_id}")

                if resource_type == "Observation":
                    code = resource.get('code', {}).get('coding', [{}])[0]
                    code_display = code.get('display', 'N/A')
                    value = resource.get('valueQuantity', {})
                    if value:
                        value_str = f"{value.get('value', 'N/A')} {value.get('unit', '')}".strip()
                    else:
                        value_str = "N/A"
                    effective = resource.get('effectiveDateTime', 'N/A')
                    print(f"      {code_display}: {value_str} ({effective})")

                elif resource_type == "Condition":
                    code = resource.get('code', {}).get('coding', [{}])[0]
                    code_display = code.get('display', 'N/A')
                    onset = resource.get('onsetDateTime', 'N/A')
                    print(f"      {code_display} (Onset: {onset})")

                elif resource_type == "Encounter":
                    enc_class = resource.get('class', {}).get('code', 'N/A')
                    period = resource.get('period', {})
                    start = period.get('start', 'N/A')
                    print(f"      Class: {enc_class}, Start: {start}")

                elif resource_type == "Procedure":
                    code = resource.get('code', {}).get('coding', [{}])[0]
                    code_display = code.get('display', 'N/A')
                    performed = resource.get('performedDateTime', resource.get('performedPeriod', {}).get('start', 'N/A'))
                    print(f"      {code_display} ({performed})")

                elif resource_type == "MedicationRequest":
                    medication = resource.get('medicationCodeableConcept', {}).get('coding', [{}])[0]
                    med_display = medication.get('display', 'N/A')
                    authored = resource.get('authoredOn', 'N/A')
                    print(f"      {med_display} (Ordered: {authored})")

                elif resource_type == "AllergyIntolerance":
                    code = resource.get('code', {}).get('coding', [{}])[0]
                    code_display = code.get('display', 'N/A')
                    print(f"      {code_display}")

                elif resource_type == "Immunization":
                    vaccine = resource.get('vaccineCode', {}).get('coding', [{}])[0]
                    vaccine_display = vaccine.get('display', 'N/A')
                    occurrence = resource.get('occurrenceDateTime', 'N/A')
                    print(f"      {vaccine_display} ({occurrence})")

                else:
                    print(f"      Resource ID: {resource_id}")

            if len(entries) > 5:
                print(f"\n  ... and {len(entries) - 5} more")

    print("\n" + "=" * 80)
    print("END OF PATIENT RECORD")
    print("=" * 80)


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

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    # If patient-id is provided, fetch all patient data
    if args.patient_id:
        since = None
        if args.years is not None:
            if args.years <= 0:
                sys.exit("--years must be a positive integer.")
            since = datetime.utcnow() - timedelta(days=365 * args.years)
            print(f"Limiting related resources to dates >= {since.date().isoformat()} ({args.years} year(s)).")
        patient_data = get_all_patient_data(fhir_url, credential, args.patient_id, since=since)
        display_patient_data(patient_data)
    else:
        # Regular resource query
        print(f"Resource type: {args.resource_type}")

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
