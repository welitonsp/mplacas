#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

readonly REQUIRED_COMMANDS=(
  "collect"
  "daily-pipeline"
  "dispatch-outbox"
  "drain-collection"
  "drain-report-exports"
  "daily-digest"
  "operational-watchdog"
  "retention"
)

load_config
require_gcloud
require_authenticated_gcloud
configure_gcloud_project
validate_monitoring_notification_channels

for command_name in "${REQUIRED_COMMANDS[@]}"; do
  name="${GCP_OPERATIONAL_JOB_PREFIX}-${command_name}"
  gcloud run jobs describe "$name" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" >/dev/null || die "missing Cloud Run Job: ${name}"
  scheduler_state="$(gcloud scheduler jobs describe "$name" \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --format='value(state)')" || die "missing Scheduler job: ${name}"
  [[ "$scheduler_state" == "ENABLED" ]] || die \
    "Scheduler job is not enabled: ${name} (${scheduler_state:-unknown})"
done

verify_monitoring_policy "operational_job_failure"
verify_monitoring_policy "operational_watchdog_absence"

SMOKE_JOB_NAME="${GCP_OPERATIONAL_JOB_PREFIX}-smoke"
gcloud run jobs describe "$SMOKE_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" >/dev/null || die "missing smoke job: ${SMOKE_JOB_NAME}"

confirm_exact \
  "SMOKE-OPERATIONS-${GCP_PROJECT_ID}" \
  "Type SMOKE-OPERATIONS-${GCP_PROJECT_ID} to execute smoke and operational watchdog jobs:"
gcloud run jobs execute "$SMOKE_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --wait

WATCHDOG_JOB_NAME="${GCP_OPERATIONAL_JOB_PREFIX}-operational-watchdog"
gcloud run jobs execute "$WATCHDOG_JOB_NAME" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --wait

log "all mandatory components are enabled; smoke and operational watchdog jobs succeeded"
