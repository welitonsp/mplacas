#!/usr/bin/env bash
# Provisions an isolated "twin" of the operational watchdog absence drill:
# a trivial Cloud Run Job (mplacas-watchdog-drill) + Cloud Scheduler trigger
# + a forked Cloud Monitoring alert policy, all living inside the SAME
# production GCP project (mplacas) as the real watchdog. See
# docs/RUNBOOK_WATCHDOG_DRILL.md for the full T0-T3 drill sequence and
# docs/ADR-063-cloud-monitoring-operational-watchdog.md for the policy this
# drill exists to prove.
#
# IMPORTANT — this is the OPPOSITE of every other guardrail in this repo:
# every other infra/gcp/*.sh script exists to protect production by
# rejecting anything that is NOT the configured project. This script does
# the reverse on purpose: it REFUSES to run against anything other than the
# real production project (mplacas). The whole point of the drill (per the
# architect-approved Plan B) is to prove that mplacas-operational-watchdog's
# absence really pages the REAL production notification channel — that can
# only be demonstrated inside the real project, so a stray/misconfigured
# project id here is treated as a configuration error, not a safety net.
#
# This script never touches the real watchdog resources
# (mplacas-operational-watchdog / operational_watchdog_absence): it only
# creates resources named *-watchdog-drill and the *_drill policy id.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/../lib.sh"

readonly DRILL_JOB_NAME="mplacas-watchdog-drill"
readonly DRILL_POLICY_ID="operational_watchdog_absence_drill"
readonly DRILL_POLICY_FILE="${SCRIPT_DIR}/../monitoring/operational-watchdog-absence-drill.json"
# Same hourly cadence as mplacas-operational-watchdog
# (infra/gcp/provision-operations.sh:OPERATIONAL_SCHEDULES). Keep in sync
# manually — the absence policy's 2h window assumes an hourly heartbeat.
readonly DRILL_SCHEDULE="5 * * * *"
# busybox:stable, pinned by digest (same pin-by-digest convention as
# infra/gcp/Dockerfile.audit and the repository root Dockerfile). No secrets,
# no business logic, no network calls — the container only needs to exit 0
# so the Cloud Run Job metric "completed_execution_count{result=succeeded}"
# has a real time series to go silent on during the drill.
readonly DRILL_IMAGE="docker.io/library/busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"

require_production_project() {
  [[ "${GCP_PROJECT_ID:-}" == "mplacas" ]] || die \
    "this drill only runs against the real production project (mplacas); got: '${GCP_PROJECT_ID:-}'"
}

deploy_drill_job() {
  gcloud run jobs deploy "$DRILL_JOB_NAME" \
    --image "$DRILL_IMAGE" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --cpu 1 \
    --memory 512Mi \
    --tasks 1 \
    --parallelism 1 \
    --max-retries 0 \
    --task-timeout 2m \
    --command sh \
    --args="-c,exit 0" \
    --quiet

  gcloud run jobs add-iam-policy-binding "$DRILL_JOB_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --member="serviceAccount:$(scheduler_service_account_email)" \
    --role="roles/run.invoker" \
    --quiet >/dev/null
}

upsert_drill_schedule() {
  local uri
  uri="https://${GCP_REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${GCP_PROJECT_ID}/jobs/${DRILL_JOB_NAME}:run"

  if gcloud scheduler jobs describe "$DRILL_JOB_NAME" \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$DRILL_JOB_NAME" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --schedule "$DRILL_SCHEDULE" \
      --time-zone "$MPLACAS_TIMEZONE" \
      --uri "$uri" \
      --http-method POST \
      --oauth-service-account-email "$(scheduler_service_account_email)" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
      --attempt-deadline 2m \
      --max-retry-attempts 1 \
      --quiet
  else
    gcloud scheduler jobs create http "$DRILL_JOB_NAME" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --schedule "$DRILL_SCHEDULE" \
      --time-zone "$MPLACAS_TIMEZONE" \
      --uri "$uri" \
      --http-method POST \
      --oauth-service-account-email "$(scheduler_service_account_email)" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
      --attempt-deadline 2m \
      --max-retry-attempts 1 \
      --quiet
  fi
}

load_config
require_production_project
require_gcloud
require_authenticated_gcloud
require_python
configure_gcloud_project
validate_billing_enabled
validate_monitoring_notification_channels
scheduler_job_is_expected "$DRILL_JOB_NAME" || die \
  "${DRILL_JOB_NAME} missing from MPLACAS_EXPECTED_SCHEDULER_JOBS (infra/gcp/lib.sh)"
ensure_scheduler_service_account

confirm_exact \
  "PROVISION-WATCHDOG-DRILL-${GCP_PROJECT_ID}" \
  "Type PROVISION-WATCHDOG-DRILL-${GCP_PROJECT_ID} to create the isolated watchdog drill job, schedule and alert policy in the REAL production project:"

deploy_drill_job
upsert_drill_schedule
upsert_monitoring_policy "$DRILL_POLICY_ID" "$DRILL_POLICY_FILE"

log "watchdog drill job, schedule and alert policy provisioned idempotently"
log "this reused the REAL production notification channel(s); no new channel was created"
log "next: follow docs/RUNBOOK_WATCHDOG_DRILL.md starting at T0"
