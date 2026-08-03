#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

fail_if_output() {
  local description="$1"
  local output="$2"

  if [[ -n "$output" ]]; then
    printf '%s\n' "$output" >&2
    die "prohibited resource detected: ${description}"
  fi
}

audit_scheduler_jobs() {
  local job_name
  local unexpected=()

  while IFS= read -r job_name; do
    [[ -n "$job_name" ]] || continue
    scheduler_job_is_expected "$job_name" || unexpected+=("$job_name")
  done < <(
    gcloud scheduler jobs list \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --filter='name~mplacas' \
      --format='value(name.basename())'
  )

  if ((${#unexpected[@]} > 0)); then
    printf '%s\n' "${unexpected[@]}" >&2
    die "prohibited resource detected: Cloud Scheduler"
  fi
  log "Cloud Scheduler jobs match the allowlist"
}

audit_secret_versions() {
  local secret_name
  local enabled_count

  for secret_name in "${MPLACAS_SECRET_NAMES[@]}"; do
    if ! gcloud secrets describe "$secret_name" \
      --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
      warn "secret not found: ${secret_name}"
      continue
    fi

    enabled_count="$(count_enabled_secret_versions "$secret_name")"
    [[ "$enabled_count" == "1" ]] || die \
      "${secret_name} must have exactly one ENABLED version"
    log "enabled versions for ${secret_name}: ${enabled_count}"
  done
}

load_config
require_gcloud
require_authenticated_gcloud
require_python
configure_gcloud_project

# Billing scope (roles/billing.viewer) lives outside the project's IAM
# policy. The automated Cloud Run Job (mplacas-cost-audit) runs under a
# project-scoped service account that deliberately does not hold it, so the
# scheduled job opts out of this single check via MPLACAS_AUDIT_SKIP_BILLING.
# Every other guardrail in this script still runs unconditionally.
if [[ "${MPLACAS_AUDIT_SKIP_BILLING:-}" == "1" ]]; then
  warn "skipping billing check (MPLACAS_AUDIT_SKIP_BILLING=1)"
else
  validate_billing_enabled
fi

if gcloud run services describe "$GCP_SERVICE_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  validate_cloud_run_limits
  log "Cloud Run service limits are within guardrails"
else
  warn "Cloud Run service not found: ${GCP_SERVICE_NAME}"
fi

if gcloud run jobs describe "$GCP_MIGRATION_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  log "Cloud Run job present: ${GCP_MIGRATION_JOB_NAME}"
fi

if api_enabled "artifactregistry.googleapis.com"; then
  gcloud artifacts repositories list \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --format='table(name,format,location)'
fi

audit_secret_versions

if api_enabled "sqladmin.googleapis.com"; then
  fail_if_output "Cloud SQL" "$(
    gcloud sql instances list \
      --project "$GCP_PROJECT_ID" \
      --filter='name~mplacas' \
      --format='value(name)'
  )"
fi

if api_enabled "compute.googleapis.com"; then
  fail_if_output "Compute Engine" "$(
    gcloud compute instances list \
      --project "$GCP_PROJECT_ID" \
      --filter='name~mplacas' \
      --format='value(name)'
  )"
  fail_if_output "Load Balancer" "$(
    gcloud compute forwarding-rules list \
      --project "$GCP_PROJECT_ID" \
      --filter='name~mplacas' \
      --format='value(name)'
  )"
fi

if api_enabled "vpcaccess.googleapis.com"; then
  fail_if_output "VPC Connector" "$(
    gcloud compute networks vpc-access connectors list \
      --region "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --filter='name~mplacas' \
      --format='value(name)'
  )"
fi

if api_enabled "cloudscheduler.googleapis.com"; then
  audit_scheduler_jobs
fi

log "cost audit completed in read-only mode"
