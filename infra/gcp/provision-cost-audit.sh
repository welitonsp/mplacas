#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

readonly AUDIT_JOB_COMMAND="cost-audit"

# Read-only roles only. This service account never receives
# roles/secretmanager.secretAccessor or roles/billing.viewer — billing scope
# is outside the project and is skipped by audit-costs.sh in job mode via
# MPLACAS_AUDIT_SKIP_BILLING=1.
readonly AUDITOR_ROLES=(
  "roles/serviceusage.serviceUsageViewer"
  "roles/run.viewer"
  "roles/cloudsql.viewer"
  "roles/compute.viewer"
  "roles/cloudscheduler.viewer"
  "roles/artifactregistry.reader"
  "roles/secretmanager.viewer"
)

audit_job_name() {
  printf '%s-%s\n' "$GCP_OPERATIONAL_JOB_PREFIX" "$AUDIT_JOB_COMMAND"
}

ensure_auditor_read_only_access() {
  local member
  local role
  member="serviceAccount:$(auditor_service_account_email)"
  for role in "${AUDITOR_ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
      --member="$member" \
      --role="$role" \
      --condition=None \
      --quiet >/dev/null
  done
  log "auditor service account holds ${#AUDITOR_ROLES[@]} read-only role(s)"
}

# gcloud builds submit --tag runs `docker build -t "$TAG" .` against the
# supplied source directory, always looking for a file literally named
# "Dockerfile" at its root. infra/gcp/Dockerfile.audit's COPY directives
# expect an infra/gcp/ prefix (so lib.sh's repo_root()/config_file() resolve
# correctly at runtime), so a scratch build context is assembled here instead
# of building from the repository root directly.
build_and_push_image() {
  local image="$1"
  local root
  local context
  root="$(repo_root)"
  context="$(mktemp -d)"
  trap 'rm -rf -- "$context"' RETURN

  mkdir -p "${context}/infra/gcp"
  cp "${root}/infra/gcp/Dockerfile.audit" "${context}/Dockerfile"
  cp "${root}/infra/gcp/audit-costs.sh" "${context}/infra/gcp/audit-costs.sh"
  cp "${root}/infra/gcp/lib.sh" "${context}/infra/gcp/lib.sh"

  gcloud builds submit "$context" \
    --project "$GCP_PROJECT_ID" \
    --tag "$image" \
    --quiet
}

deploy_audit_job() {
  local image="$1"
  local name
  name="$(audit_job_name)"

  gcloud run jobs deploy "$name" \
    --image "$image" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --service-account "$(auditor_service_account_email)" \
    --cpu "$GCP_CPU" \
    --memory "$GCP_MEMORY" \
    --tasks 1 \
    --parallelism 1 \
    --max-retries 1 \
    --task-timeout 10m \
    --set-env-vars "MPLACAS_ENVIRONMENT=production,MPLACAS_GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=${GCP_REGION},GCP_SERVICE_NAME=${GCP_SERVICE_NAME},GCP_MIGRATION_JOB_NAME=${GCP_MIGRATION_JOB_NAME},GCP_RUNTIME_SERVICE_ACCOUNT=${GCP_RUNTIME_SERVICE_ACCOUNT},GCP_SCHEDULER_SERVICE_ACCOUNT=${GCP_SCHEDULER_SERVICE_ACCOUNT},GCP_OPERATIONAL_JOB_PREFIX=${GCP_OPERATIONAL_JOB_PREFIX},GCP_MIN_INSTANCES=${GCP_MIN_INSTANCES},GCP_MAX_INSTANCES=${GCP_MAX_INSTANCES},GCP_CPU=${GCP_CPU},GCP_MEMORY=${GCP_MEMORY},GCP_CONCURRENCY=${GCP_CONCURRENCY},GCP_REQUEST_TIMEOUT=${GCP_REQUEST_TIMEOUT},MPLACAS_TIMEZONE=${MPLACAS_TIMEZONE},MPLACAS_DASHBOARD_URL=${MPLACAS_DASHBOARD_URL},MPLACAS_CONFIG_FROM_ENV=1,MPLACAS_AUDIT_SKIP_BILLING=1" \
    --command bash \
    --args=infra/gcp/audit-costs.sh \
    --quiet

  gcloud run jobs add-iam-policy-binding "$name" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --member="serviceAccount:$(scheduler_service_account_email)" \
    --role="roles/run.invoker" \
    --quiet >/dev/null
}

upsert_audit_schedule() {
  local name
  local uri
  name="$(audit_job_name)"
  uri="https://${GCP_REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${GCP_PROJECT_ID}/jobs/${name}:run"

  if gcloud scheduler jobs describe "$name" \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$name" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --schedule "0 4 * * *" \
      --time-zone "$MPLACAS_TIMEZONE" \
      --uri "$uri" \
      --http-method POST \
      --oauth-service-account-email "$(scheduler_service_account_email)" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
      --attempt-deadline 10m \
      --max-retry-attempts 1 \
      --quiet
  else
    gcloud scheduler jobs create http "$name" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --schedule "0 4 * * *" \
      --time-zone "$MPLACAS_TIMEZONE" \
      --uri "$uri" \
      --http-method POST \
      --oauth-service-account-email "$(scheduler_service_account_email)" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
      --attempt-deadline 10m \
      --max-retry-attempts 1 \
      --quiet
  fi
}

load_config
require_gcloud
require_authenticated_gcloud
require_python
configure_gcloud_project
validate_billing_enabled
scheduler_job_is_expected "$(audit_job_name)" || die \
  "$(audit_job_name) missing from MPLACAS_EXPECTED_SCHEDULER_JOBS"
ensure_auditor_service_account
ensure_scheduler_service_account

confirm_exact \
  "PROVISION-COST-AUDIT-${GCP_PROJECT_ID}" \
  "Type PROVISION-COST-AUDIT-${GCP_PROJECT_ID} to deploy the automated audit job and schedule:"

ensure_auditor_read_only_access

IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run-source-deploy/$(audit_job_name)"
build_and_push_image "$IMAGE"
deploy_audit_job "$IMAGE"
upsert_audit_schedule

log "automated cost-audit job and daily schedule provisioned idempotently"
log "the auditor service account never holds secretAccessor or billing.viewer"
