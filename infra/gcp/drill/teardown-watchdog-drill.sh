#!/usr/bin/env bash
# Symmetric teardown for infra/gcp/drill/provision-watchdog-drill.sh: removes
# the drill Cloud Scheduler job, the drill Cloud Run Job and the forked drill
# alert policy. The production notification channel(s) configured in
# GCP_MONITORING_NOTIFICATION_CHANNELS are never touched — they are real
# production channels, not drill resources.
#
# IMPORTANT — same as provision-watchdog-drill.sh, this is the OPPOSITE of
# every other guardrail in this repo: it REFUSES to run against anything
# other than the real production project (mplacas), on purpose, because the
# drill resources only ever exist there.
#
# Run this within 48h of an approved drill (docs/RUNBOOK_WATCHDOG_DRILL.md,
# decommissioning step). This script does NOT remove the temporary
# "mplacas-watchdog-drill" entry from MPLACAS_EXPECTED_SCHEDULER_JOBS in
# infra/gcp/lib.sh — editing a bash array via script is fragile and error
# prone, so removal is manual. See the reminder printed at the end.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/../lib.sh"

readonly DRILL_JOB_NAME="mplacas-watchdog-drill"
readonly DRILL_POLICY_ID="operational_watchdog_absence_drill"

require_production_project() {
  [[ "${GCP_PROJECT_ID:-}" == "mplacas" ]] || die \
    "this drill only runs against the real production project (mplacas); got: '${GCP_PROJECT_ID:-}'"
}

delete_drill_policy() {
  local policy_name
  policy_name="$(find_monitoring_policy "$DRILL_POLICY_ID")"
  if [[ -z "$policy_name" ]]; then
    log "drill alert policy already absent: ${DRILL_POLICY_ID}"
    return
  fi
  gcloud monitoring policies delete "$policy_name" \
    --project "$GCP_PROJECT_ID" \
    --quiet
  log "drill alert policy deleted: ${DRILL_POLICY_ID}"
}

delete_drill_schedule() {
  if gcloud scheduler jobs describe "$DRILL_JOB_NAME" \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud scheduler jobs delete "$DRILL_JOB_NAME" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --quiet
    log "drill Scheduler job deleted: ${DRILL_JOB_NAME}"
  else
    log "drill Scheduler job already absent: ${DRILL_JOB_NAME}"
  fi
}

delete_drill_job() {
  if gcloud run jobs describe "$DRILL_JOB_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud run jobs delete "$DRILL_JOB_NAME" \
      --region "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --quiet
    log "drill Cloud Run Job deleted: ${DRILL_JOB_NAME}"
  else
    log "drill Cloud Run Job already absent: ${DRILL_JOB_NAME}"
  fi
}

load_config
require_production_project
require_gcloud
require_authenticated_gcloud
require_python
configure_gcloud_project

confirm_exact \
  "TEARDOWN-WATCHDOG-DRILL-${GCP_PROJECT_ID}" \
  "Type TEARDOWN-WATCHDOG-DRILL-${GCP_PROJECT_ID} to remove the watchdog drill job, schedule and alert policy:"

# Pause the schedule first so no execution races the deletes below.
if gcloud scheduler jobs describe "$DRILL_JOB_NAME" \
  --location "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud scheduler jobs pause "$DRILL_JOB_NAME" \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --quiet >/dev/null || true
fi

delete_drill_schedule
delete_drill_job
delete_drill_policy

log "watchdog drill resources removed; the real production notification channel(s) were not touched"
warn "MANUAL STEP REQUIRED: remove the temporary 'mplacas-watchdog-drill' entry from"
warn "MPLACAS_EXPECTED_SCHEDULER_JOBS in infra/gcp/lib.sh now that the drill Scheduler"
warn "job no longer exists. Leaving it there after this teardown would let a future"
warn "stray job with that same name silently pass audit-costs.sh's guardrail."
