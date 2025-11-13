#!/usr/bin/env bash
set -euo pipefail

# Deploy the Care Manager Copilot app code to Azure App Service
# Run scripts/setup_infrastructure.sh first if this is a new deployment

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

echo "Packaging application..."
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

echo "Package created: ${ZIP_PATH}"

az account set --subscription "${SUBSCRIPTION_ID}"

echo "Deploying to ${WEB_APP}..."
az webapp deploy \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${WEB_APP}" \
    --src-path "${ZIP_PATH}" \
    --type zip \
    --async

echo ""
echo "Deployment initiated successfully!"
echo "The deployment is running asynchronously in the background."
echo ""
echo "App URL: https://$(az webapp show --name ${WEB_APP} --resource-group ${RESOURCE_GROUP} --query defaultHostName -o tsv)"
echo ""
echo "To monitor deployment logs, run:"
echo "  az webapp log tail --name ${WEB_APP} --resource-group ${RESOURCE_GROUP}"
