"""
Flask API for Care Manager Copilot

Provides REST endpoints for the web chat interface.
"""

import os
import json
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from fhir_service import FHIRCareManagerService
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# Load environment variables
load_dotenv()

def configure_aoai_key_from_key_vault():
    """
    Hydrate AOAI_API_KEY from Azure Key Vault if configuration is provided.
    """
    vault_name = os.environ.get('AZURE_KEY_VALUT') or os.environ.get('AZURE_KEY_VAULT')
    secret_name = os.environ.get('AOAI_API_KEY_NAME')

    # Nothing to do if key vault lookup is not configured
    if not vault_name or not secret_name:
        return

    vault_url = vault_name.rstrip('/')
    if '://' not in vault_url:
        vault_url = f"https://{vault_url}.vault.azure.net"

    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        secret = client.get_secret(secret_name).value
        os.environ['AOAI_API_KEY'] = secret
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch AOAI API key '{secret_name}' from Key Vault '{vault_name}': {exc}"
        ) from exc


# Initialize Flask app
app = Flask(__name__, static_folder='static')
CORS(app)

configure_aoai_key_from_key_vault()

# Initialize FHIR service (lazy loading to handle missing env vars gracefully)
fhir_service = None


def get_fhir_service():
    """Lazy initialization of FHIR service."""
    global fhir_service
    if fhir_service is None:
        try:
            fhir_service = FHIRCareManagerService()
        except KeyError as e:
            raise RuntimeError(
                f"Missing required environment variable: {e}. "
                "Please copy .env.template to .env and fill in the values."
            )
    return fhir_service


def _sse_event(event_name, payload):
    """Serialize payload as an SSE event."""
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


@app.route('/')
def index():
    """Serve the main page."""
    return send_from_directory('static', 'index.html')


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "Care Manager Copilot",
        "version": "1.0.0"
    })


@app.route('/api/patient/<patient_id>/brief', methods=['GET'])
def get_patient_brief(patient_id):
    """
    Get care manager briefing for a patient.

    Args:
        patient_id: Patient identifier from URL path

    Returns:
        JSON response with briefing or error
    """
    try:
        service = get_fhir_service()
        result = service.generate_care_manager_brief(patient_id)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/patient/<patient_id>/brief/stream', methods=['GET'])
def stream_patient_brief(patient_id):
    """Stream briefing generation progress and result via Server-Sent Events."""

    def generate_stream():
        try:
            service = get_fhir_service()
            yield _sse_event('status', {
                "stage": "fhir",
                "message": f"Querying FHIR for patient {patient_id}..."
            })

            bundle = service.fetch_patient_bundle(patient_id)
            entry_count = len(bundle.get("entry", []))

            yield _sse_event('fhir_data', {
                "stage": "fhir",
                "message": f"FHIR sync returned {entry_count} resources.",
                "patient_id": patient_id,
                "bundle_entry_count": entry_count,
                "bundle": bundle
            })

            yield _sse_event('status', {
                "stage": "prompt",
                "message": f"FHIR sync returned {entry_count} resources. Preparing Azure OpenAI prompt..."
            })

            yield _sse_event('status', {
                "stage": "llm",
                "message": "Prompting Azure OpenAI for the outreach briefing..."
            })

            briefing = service.summarize_for_care_manager(bundle)

            yield _sse_event('complete', {
                "success": True,
                "patient_id": patient_id,
                "briefing": briefing,
                "bundle_entry_count": entry_count
            })
        except Exception as exc:
            yield _sse_event('failure', {
                "success": False,
                "patient_id": patient_id,
                "error": str(exc)
            })

    response = Response(stream_with_context(generate_stream()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.route('/api/patients', methods=['GET'])
def list_patients():
    """Return a roster of patients with demographics for the UI grid."""
    try:
        raw_limit = request.args.get('count', 25)
        limit = max(1, min(100, int(raw_limit)))
    except ValueError:
        return jsonify({
            "success": False,
            "error": "count must be an integer"
        }), 400

    try:
        service = get_fhir_service()
        patients = service.list_patients(limit)
        return jsonify({
            "success": True,
            "patients": patients
        })
    except RuntimeError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat endpoint for processing member ID queries.

    Expected JSON body:
    {
        "member_id": "patient-123"
    }

    Returns:
        JSON response with care manager briefing
    """
    try:
        data = request.get_json()
        member_id = data.get('member_id', '').strip()

        if not member_id:
            return jsonify({
                "success": False,
                "error": "member_id is required"
            }), 400

        service = get_fhir_service()
        result = service.generate_care_manager_brief(member_id)
        return jsonify(result)

    except RuntimeError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500


if __name__ == '__main__':
    # Check for required environment variables
    required_vars = ['FHIR_URL', 'AOAI_ENDPOINT', 'AOAI_DEPLOYMENT']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        print("ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease copy .env.template to .env and fill in the values.")
        exit(1)

    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
