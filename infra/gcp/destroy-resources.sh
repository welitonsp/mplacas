#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

DELETE_SECRETS=false
for arg in "$@"; do
  case "$arg" in
    --delete-secrets) DELETE_SECRETS=true ;;
    *) die "unknown argument: ${arg}" ;;
  esac
done

load_config
require_gcloud
require_authenticated_gcloud
configure_gcloud_project

log "Mplacas resources selected in project ${GCP_PROJECT_ID}:"
gcloud run services list \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --filter="metadata.name=${GCP_SERVICE_NAME}"
gcloud run jobs list \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --filter="metadata.name=${GCP_MIGRATION_JOB_NAME}"

if [[ "$DELETE_SECRETS" == "true" ]]; then
  warn "named Mplacas secrets will also be deleted"
else
  log "Secret Manager secrets will be preserved by default"
fi

confirm_exact \
  "DELETE-MPLACAS-${GCP_PROJECT_ID}" \
  "Type DELETE-MPLACAS-${GCP_PROJECT_ID} to remove only Mplacas runtime resources:"

if gcloud run jobs describe "$GCP_MIGRATION_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud run jobs delete "$GCP_MIGRATION_JOB_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --quiet
fi

if gcloud run services describe "$GCP_SERVICE_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud run services delete "$GCP_SERVICE_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --quiet
fi

if [[ "$DELETE_SECRETS" == "true" ]]; then
  for secret_name in "${MPLACAS_SECRET_NAMES[@]}"; do
    if gcloud secrets describe "$secret_name" \
      --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
      gcloud secrets delete "$secret_name" \
        --project "$GCP_PROJECT_ID" \
        --quiet
    fi
  done
fi

warn "Artifact Registry is never deleted automatically; review images manually"
log "cleanup completed; project and billing were preserved"
