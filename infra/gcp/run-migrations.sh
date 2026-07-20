#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

load_config
require_gcloud
require_authenticated_gcloud
configure_gcloud_project
validate_billing_enabled
ensure_runtime_service_account

for secret_name in "$SECRET_MIGRATION_DATABASE_URL" "$SECRET_OPERATIONS_KEY"; do
  gcloud secrets describe "$secret_name" --project "$GCP_PROJECT_ID" >/dev/null
  [[ "$(count_enabled_secret_versions "$secret_name")" == "1" ]] || die \
    "${secret_name} must have exactly one ENABLED version before migrations"
done

IMAGE="$(cloud_run_service_image)"
[[ -n "$IMAGE" ]] || die "deployed service image was not found"

confirm_exact \
  "MIGRATE-MPLACAS-${GCP_PROJECT_ID}" \
  "Type MIGRATE-MPLACAS-${GCP_PROJECT_ID} to run database migrations:"

gcloud run jobs deploy "$GCP_MIGRATION_JOB_NAME" \
  --image "$IMAGE" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --service-account "$(runtime_service_account_email)" \
  --cpu "$GCP_CPU" \
  --memory "$GCP_MEMORY" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout 10m \
  --set-env-vars \
    "MPLACAS_ENVIRONMENT=production,MPLACAS_TIMEZONE=${MPLACAS_TIMEZONE},MPLACAS_GCP_PROJECT_ID=${GCP_PROJECT_ID},MPLACAS_CLOUD_TRACE_ENABLED=true" \
  --set-secrets \
    "MPLACAS_DATABASE_URL=${SECRET_MIGRATION_DATABASE_URL}:latest,MPLACAS_OPERATIONS_API_KEY=${SECRET_OPERATIONS_KEY}:latest" \
  --command python \
  --args=-m,mplacas.cloud_jobs,migrate \
  --quiet

gcloud run jobs execute "$GCP_MIGRATION_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --wait

log "database migration job completed"
