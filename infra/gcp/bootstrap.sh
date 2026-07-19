#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

PROJECT_ARG="${1:-}"
[[ -n "$PROJECT_ARG" ]] || die "usage: infra/gcp/bootstrap.sh <project-id>"

load_config
[[ "$PROJECT_ARG" == "$GCP_PROJECT_ID" ]] || die \
  "project argument must match GCP_PROJECT_ID"
require_gcloud
require_authenticated_gcloud

log "selected project: ${GCP_PROJECT_ID}"
confirm_exact \
  "$GCP_PROJECT_ID" \
  "Type the project id to configure Google Cloud resources:"

configure_gcloud_project
validate_billing_enabled

gcloud services enable "${MPLACAS_REQUIRED_APIS[@]}" \
  --project "$GCP_PROJECT_ID"
ensure_runtime_service_account
ensure_runtime_trace_access

log "bootstrap completed without creating service-account keys"
