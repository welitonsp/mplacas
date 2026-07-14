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
    "MPLACAS_ENVIRONMENT=production,MPLACAS_TIMEZONE=${MPLACAS_TIMEZONE}" \
  --set-secrets \
    "MPLACAS_DATABASE_URL=mplacas-database-url:latest,MPLACAS_OPERATIONS_API_KEY=mplacas-operations-api-key:latest" \
  --command python \
  --args=-m,mplacas.cloud_jobs,migrate \
  --quiet

gcloud run jobs execute "$GCP_MIGRATION_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --wait

log "database migration job completed"
