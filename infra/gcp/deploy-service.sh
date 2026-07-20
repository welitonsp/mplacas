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

for secret_name in \
  "$SECRET_DATABASE_URL" \
  "$SECRET_MIGRATION_DATABASE_URL" \
  "$SECRET_OPERATIONS_KEY" \
  "$SECRET_JWT"; do
  gcloud secrets describe "$secret_name" --project "$GCP_PROJECT_ID" >/dev/null
  require_single_enabled_secret "$secret_name"
done

validate_cors_origins "${MPLACAS_CORS_ALLOWED_ORIGINS:-}"

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
    "MPLACAS_ENVIRONMENT=production,MPLACAS_TIMEZONE=${MPLACAS_TIMEZONE},MPLACAS_GCP_PROJECT_ID=${GCP_PROJECT_ID},MPLACAS_CLOUD_TRACE_ENABLED=true,MPLACAS_CLOUD_METRICS_ENABLED=true,MPLACAS_CORS_ALLOWED_ORIGINS=${MPLACAS_CORS_ALLOWED_ORIGINS}" \
  --set-secrets \
    "MPLACAS_DATABASE_URL=${SECRET_DATABASE_URL}:latest,MPLACAS_OPERATIONS_API_KEY=${SECRET_OPERATIONS_KEY}:latest,MPLACAS_JWT_SECRET=${SECRET_JWT}:latest" \
  --allow-unauthenticated \
  --quiet

validate_cloud_run_limits
log "service deployed with guardrails enforced"
log "service URL: $(cloud_run_service_url)"
