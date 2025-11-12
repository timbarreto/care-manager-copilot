# Care Manager Copilot - FHIR Demo

A web chat application that pulls member FHIR data and generates care manager briefings using Azure OpenAI.

## What It Does

A web chat where you enter a member ID (synthetic). The bot pulls the member's FHIR data (conditions, meds, encounters, observations, care plans) and returns a case-manager briefing plus next-best actions and a call script. This aligns with HCBS/case-management focus.

## Features

- Fetches comprehensive FHIR patient data from Azure Health Data Services
- Generates care manager briefings using Azure OpenAI
- Identifies Social Determinants of Health (SDoH) and medication risks
- Provides next-best outreach actions
- Creates bilingual (English/Spanish) phone call scripts
- Works with synthetic data (Synthea) for safe demonstrations

## Prerequisites

### Azure Resources Required

1. **Azure Health Data Services (AHDS) - FHIR Service**
   - Deployed FHIR service workspace
   - FHIR service URL (e.g., `https://<workspace>-<service>.healthcareapis.azure.com`)
   - [Setup Guide](https://learn.microsoft.com/en-us/azure/healthcare-apis/fhir/get-started-with-fhir)

2. **Synthetic FHIR Data (Synthea)**
   - Generated synthetic patient data
   - Loaded into FHIR service via `$import` or FHIR Loader
   - [Synthea Documentation](https://synthetichealth.github.io/synthea/)
   - [FHIR Import Guide](https://learn.microsoft.com/en-us/azure/healthcare-apis/fhir/import-data)

3. **Azure OpenAI Service**
   - Deployed Azure OpenAI resource
   - Model deployment (recommended: `gpt-4o` or `gpt-4o-mini`)
   - [Azure OpenAI Quickstart](https://learn.microsoft.com/en-us/azure/ai-services/openai/quickstart)

### Authentication

This application uses **Azure Entra ID (formerly Azure AD)** authentication:
- `DefaultAzureCredential` for local development (uses Azure CLI login)
- Managed Identity for production deployments
- Service Principal for CI/CD scenarios

## Setup Instructions

### 1. Open in Dev Container (Recommended)

This repository includes a complete VS Code dev container configuration.

1. **Prerequisites:**
   - Docker Desktop installed and running
   - VS Code with "Dev Containers" extension installed

2. **Open in Container:**
   ```bash
   # Clone the repository (if not already done)
   git clone https://github.com/timbarreto/care-manager-copilot.git
   cd care-manager-copilot

   # Open in VS Code
   code .
   ```

3. **Reopen in Container:**
   - Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
   - Type "Dev Containers: Reopen in Container"
   - Wait for container to build (first time takes a few minutes)

### 2. Configure Environment Variables

1. **Copy the template:**
   ```bash
   cp .env.template .env
   ```

2. **Fill in your Azure resource values:**
   ```bash
   # Edit .env file
   FHIR_URL=https://your-workspace-fhir.healthcareapis.azure.com
   AOAI_ENDPOINT=https://your-openai-resource.openai.azure.com
   AOAI_DEPLOYMENT=gpt-4o-mini
   AOAI_API_KEY=your-api-key-or-leave-empty-for-managed-identity
   ```

### 3. Authenticate with Azure

For local development using Azure CLI:

```bash
# Login to Azure
az login

# Set your subscription
az account set --subscription "your-subscription-id"
```

### 4. Install Dependencies

If not using dev container:

```bash
pip install -r requirements.txt
```

### 5. Run the Application

```bash
python app.py
```

The application will start on `http://localhost:8000`

### 6. Test the Application

1. Open your browser to `http://localhost:8000`
2. Enter a synthetic patient ID (from your Synthea data loaded into FHIR)
3. Click "Get Briefing"
4. View the generated care manager briefing

## Project Structure

```
care-manager-copilot/
├── .devcontainer/
│   ├── devcontainer.json    # Dev container configuration
│   └── Dockerfile            # Container image definition
├── static/
│   └── index.html            # Web chat interface
├── app.py                    # Flask API application
├── fhir_service.py          # FHIR service and Azure OpenAI logic
├── requirements.txt          # Python dependencies
├── .env.template            # Environment variables template
├── .gitignore               # Git ignore rules
└── README.md                # This file
```

## API Endpoints

### GET /health
Health check endpoint
```json
{
  "status": "healthy",
  "service": "Care Manager Copilot",
  "version": "1.0.0"
}
```

### POST /api/chat
Generate care manager briefing
```json
// Request
{
  "member_id": "patient-123"
}

// Response
{
  "patient_id": "patient-123",
  "success": true,
  "briefing": "...",
  "bundle_entry_count": 45
}
```

### GET /api/patient/{patient_id}/brief
Alternative endpoint using path parameter

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black .
```

### Linting
```bash
pylint *.py
```

## Security Considerations

- Never commit `.env` files with real credentials
- Use Managed Identity in production environments
- AHDS FHIR service is HIPAA-eligible when properly configured
- This demo uses synthetic data only
- Implement proper RBAC for FHIR and Azure OpenAI access

## Loading Synthetic Data

### Option 1: Using $import (Fast)

1. Generate Synthea NDJSON data
2. Upload to Azure Blob Storage
3. Use FHIR `$import` operation
   - [Import Documentation](https://learn.microsoft.com/en-us/azure/healthcare-apis/fhir/import-data)

### Option 2: Using FHIR Loader

1. Deploy the OSS FHIR Loader
2. Drop Synthea bundles into designated blob container
3. Loader automatically pushes to FHIR service
   - [FHIR Loader on GitHub](https://github.com/microsoft/fhir-loader)

## Troubleshooting

### Authentication Issues

```
Error: Missing required environment variable
```
- Ensure `.env` file exists and has all required variables
- Run `az login` to authenticate with Azure

### FHIR Access Denied

```
401 Unauthorized
```
- Verify your account has FHIR Data Contributor role
- Check FHIR_URL is correct
- Ensure `az login` is using correct subscription

### Azure OpenAI Errors

```
Rate limit exceeded
```
- Check your Azure OpenAI quota
- Consider using a lower-tier model or request quota increase

## Resources

- [Azure Health Data Services Documentation](https://learn.microsoft.com/en-us/azure/healthcare-apis/)
- [FHIR Specification](https://hl7.org/fhir/)
- [Synthea Patient Generator](https://synthetichealth.github.io/synthea/)
- [Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
- [FHIR Postman Samples](https://github.com/microsoft/fhir-server-samples)

## License

MIT

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
