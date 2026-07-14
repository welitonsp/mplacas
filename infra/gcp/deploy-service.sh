#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

require_single_enabled_secret() {
  local secret_name="$1"
  local enabled_count

  enabled_count="$(count_enabled_secret_versions "$secret_name")"
  [[ "$enabled_count" == "1" ]] || die \
    "${secret_name} must have exactly one ENABLED version before deployment"
}

load_config
require_gcloud
require_authenticated_gcloud
require_python
configure_gcloud_project
validate_billing_enabled
ensure_runtime_service_account

for secret_name in "${MPLACAS_SECRET_NAMES[@]}"; do
  gcloud secrets describe "$secret_name" \
    --project "$GCP_PROJECT_ID" >/dev/null
  require_single_enabled_secret "$secret_name"
done

confirm_exact \
  "DEPLOY-MPLACAS-${GCP_PROJECT_ID}" \
  "Type DEPLOY-MPLACAS-${GCP_PROJECT_ID} to deploy the service:"

gcloud run deploy "$GCP_SERVICE_NAME" \
  --source "$(repo_root)" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --service-account "$(runtime_service_account_email)" \
  --min-instances "$GCP_MIN_INSTANCES" \
  --max-instances "$GCP_MAX_INSTANCES" \
  --cpu "$GCP_CPU" \
  --memory "$GCP_MEMORY" \
  --concurrency "$GCP_CONCURRENCY" \
  --timeout "$GCP_REQUEST_TIMEOUT" \
  --set-env-vars \
    "MPLACAS_ENVIRONMENT=production,MPLACAS_TIMEZONE=${MPLACAS_TIMEZONE}" \
  --set-secrets \
    "MPLACAS_DATABASE_URL=mplacas-database-url:latest,MPLACAS_OPERATIONS_API_KEY=mplacas-operations-api-key:latest" \
  --allow-unauthenticated \
  --quiet

validate_cloud_run_limits
log "service deployed with guardrails enforced"
log "service URL: $(cloud_run_service_url)"
