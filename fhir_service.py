"""
FHIR Care Manager Copilot Service

This module fetches patient FHIR data from Azure Health Data Services
and uses Azure OpenAI to generate care manager briefings.
"""

import os
import json
import requests
from typing import Dict, Any, List, Optional
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI


class FHIRCareManagerService:
    """Service for fetching FHIR data and generating care manager briefings."""

    def __init__(self):
        self.fhir_url = os.environ["FHIR_URL"].rstrip("/")
        self.aoai_endpoint = os.environ["AOAI_ENDPOINT"]
        self.aoai_deployment = os.environ["AOAI_DEPLOYMENT"]
        self.credential = DefaultAzureCredential()

        # Initialize Azure OpenAI client
        aoai_api_key = os.environ.get("AOAI_API_KEY")
        if aoai_api_key:
            self.aoai_client = AzureOpenAI(
                azure_endpoint=self.aoai_endpoint,
                api_version="2024-10-01-preview",
                api_key=aoai_api_key
            )
        else:
            # Use Managed Identity
            self.aoai_client = AzureOpenAI(
                azure_endpoint=self.aoai_endpoint,
                api_version="2024-10-01-preview",
                azure_ad_token_provider=lambda: self.credential.get_token(
                    "https://cognitiveservices.azure.com/.default"
                ).token
            )

    def fetch_patient_bundle(self, patient_id: str) -> Dict[str, Any]:
        """
        Fetch patient FHIR bundle including related clinical resources.

        Args:
            patient_id: The patient identifier

        Returns:
            FHIR Bundle as a dictionary
        """
        # Get Entra ID token for FHIR
        token = self.credential.get_token(f"{self.fhir_url}/.default").token

        # Build search query with _revinclude to pull related resources
        url = (
            f"{self.fhir_url}/Patient"
            f"?_id={patient_id}"
            f"&_revinclude=Condition:subject"
            f"&_revinclude=MedicationRequest:subject"
            f"&_revinclude=Observation:subject"
            f"&_revinclude=Encounter:subject"
            f"&_revinclude=CarePlan:subject"
            f"&_count=200"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json"
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()

    def summarize_for_care_manager(self, bundle_json: Dict[str, Any]) -> str:
        """
        Use Azure OpenAI to generate a care manager briefing from FHIR data.

        Args:
            bundle_json: FHIR Bundle containing patient data

        Returns:
            Care manager briefing as text
        """
        system_prompt = (
            "You are a care-management assistant for community-based services. "
            "From the FHIR bundle, produce: "
            "(1) concise member overview; "
            "(2) key risks & SDoH (Social Determinants of Health); "
            "(3) 3 next-best outreach actions; "
            "(4) a short phone script in English and Spanish. "
            "Avoid clinical advice; stick to the facts in the data."
        )

        # Truncate bundle to fit token limits (keeping first 150k chars)
        bundle_str = json.dumps(bundle_json, indent=2)[:150000]
        user_prompt = f"FHIR bundle JSON:\n```json\n{bundle_str}\n```"

        response = self.aoai_client.chat.completions.create(
            model=self.aoai_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            # Note: temperature parameter removed as gpt-5-mini only supports default (1)
        )

        return response.choices[0].message.content

    def generate_care_manager_brief(self, patient_id: str) -> Dict[str, Any]:
        """
        Main method to fetch patient data and generate care manager briefing.

        Args:
            patient_id: The patient identifier

        Returns:
            Dictionary containing patient_id, bundle, and briefing
        """
        try:
            # Fetch FHIR bundle
            bundle = self.fetch_patient_bundle(patient_id)

            # Generate briefing
            briefing = self.summarize_for_care_manager(bundle)

            return {
                "patient_id": patient_id,
                "success": True,
                "briefing": briefing,
                "bundle_entry_count": len(bundle.get("entry", []))
            }
        except Exception as e:
            return {
                "patient_id": patient_id,
                "success": False,
                "error": str(e)
            }

    def list_patients(self, limit: int = 25) -> List[Dict[str, Optional[str]]]:
        """
        Retrieve a roster of patients with name and date of birth for quick selection.

        Args:
            limit: Maximum number of patients to return.

        Returns:
            A list of patient dictionaries containing id, name, birth_date, and gender.
        """
        # Get Entra ID token for FHIR
        token = self.credential.get_token(f"{self.fhir_url}/.default").token

        # Basic roster query
        url = f"{self.fhir_url}/Patient?_count={limit}&_sort=name"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json"
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        bundle = response.json()

        roster: List[Dict[str, Optional[str]]] = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            patient_id = resource.get("id")

            name = self._format_patient_name(resource.get("name", []))
            roster.append({
                "patient_id": patient_id,
                "name": name or "Unnamed patient",
                "birth_date": resource.get("birthDate"),
                "gender": resource.get("gender")
            })

        return roster

    @staticmethod
    def _format_patient_name(name_entries: List[Dict[str, Any]]) -> Optional[str]:
        """Compose a readable patient name from FHIR Person.name entries."""
        if not name_entries:
            return None

        primary = name_entries[0]
        given = " ".join(primary.get("given", [])).strip()
        family = primary.get("family", "").strip()

        if given and family:
            return f"{given} {family}"
        return given or family or None
