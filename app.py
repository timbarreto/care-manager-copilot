"""
Flask API for Care Manager Copilot

Provides REST endpoints for the web chat interface.
"""

import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from fhir_service import FHIRCareManagerService

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='static')
CORS(app)

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
