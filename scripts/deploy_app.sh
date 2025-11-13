#!/usr/bin/env bash
set -euo pipefail

# Deploy the Care Manager Copilot app to Azure App Service using settings from .env

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Copy .env.template and update the deployment settings." >&2
    exit 1
fi

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

command -v az >/dev/null 2>&1 || {
    echo "Azure CLI (az) is required on PATH." >&2
    exit 1
}

: "${SUBSCRIPTION_ID:?SUBSCRIPTION_ID must be set in .env}"
: "${RESOURCE_GROUP:?RESOURCE_GROUP must be set in .env}"
: "${WEB_APP:?WEB_APP must be set in .env}"

DIST_DIR="${REPO_ROOT}/dist"
ZIP_PATH="${DIST_DIR}/care-manager-copilot.zip"

rm -rf "${ZIP_PATH}" "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

pushd "${REPO_ROOT}" >/dev/null
zip -r "${ZIP_PATH}" \
    app.py \
    fhir_service.py \
    requirements.txt \
    static \
    README.md \
    .env.template >/dev/null
popd >/dev/null

az account set --subscription "${SUBSCRIPTION_ID}"

echo "Enabling managed identity for ${WEB_APP}..."
az webapp identity assign \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEB_APP}" >/dev/null

PRINCIPAL_ID=$(az webapp identity show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEB_APP}" \
    --query principalId -o tsv)

echo "Managed identity enabled. Principal ID: ${PRINCIPAL_ID}"

if [[ -n "${AZURE_KEY_VAULT}" ]]; then
    echo "Granting Key Vault access to managed identity..."

    # Get Key Vault resource ID
    KV_ID=$(az keyvault show --name "${AZURE_KEY_VAULT}" --query id -o tsv)

    # Assign Key Vault Secrets User role (RBAC)
    az role assignment create \
        --role "Key Vault Secrets User" \
        --assignee-object-id "${PRINCIPAL_ID}" \
        --assignee-principal-type ServicePrincipal \
        --scope "${KV_ID}" 2>/dev/null || echo "Role already assigned or using access policies."

    echo "Key Vault access configured."
fi

echo "Configuring app settings..."
az webapp config appsettings set \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEB_APP}" \
    --settings \
        SCM_DO_BUILD_DURING_DEPLOYMENT=true \
        FHIR_URL="${FHIR_URL}" \
        AOAI_ENDPOINT="${AOAI_ENDPOINT}" \
        AOAI_DEPLOYMENT="${AOAI_DEPLOYMENT}" \
        AOAI_API_KEY_NAME="${AOAI_API_KEY_NAME}" \
        AZURE_KEY_VAULT="${AZURE_KEY_VAULT}" \
        AZURE_TENANT_ID="${AZURE_TENANT_ID}" >/dev/null

echo "App settings configured."

az webapp config set \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEB_APP}" \
    --startup-file "python app.py" >/dev/null

az webapp deploy \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEB_APP}" \
    --src-path "${ZIP_PATH}" \
    --type zip

echo "Deployment completed. Package: ${ZIP_PATH}"
