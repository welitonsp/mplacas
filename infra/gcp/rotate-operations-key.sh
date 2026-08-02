#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

load_config
require_gcloud
require_authenticated_gcloud
require_curl
require_python
configure_gcloud_project

confirmation="rotate-${GCP_PROJECT_ID}-${GCP_SERVICE_NAME}"
confirm_exact \
  "$confirmation" \
  "Type ${confirmation} to rotate the production operations key"

previous_version="$(
  gcloud secrets versions list "$SECRET_OPERATIONS_KEY" \
    --project "$GCP_PROJECT_ID" \
    --filter='state=ENABLED' \
    --sort-by='~createTime' \
    --limit=1 \
    --format='value(name.basename())'
)"
[[ "$previous_version" =~ ^[0-9]+$ ]] || die \
  "enabled operations key version not found"

previous_key="$(
  gcloud secrets versions access "$previous_version" \
    --secret "$SECRET_OPERATIONS_KEY" \
    --project "$GCP_PROJECT_ID" \
    --quiet
)"
new_key="$(python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_urlsafe(48))')"
[[ "${#new_key}" -ge 64 ]] || die "generated operations key is unexpectedly short"

new_version=""
rotation_committed="false"

clear_sensitive_values() {
  unset previous_key new_key
}

rollback_rotation() {
  local failure_status=$?
  if [[ "$rotation_committed" != "true" && "$new_version" =~ ^[0-9]+$ ]]; then
    warn "rotation failed; restoring operations key version ${previous_version}"
    gcloud run services update "$GCP_SERVICE_NAME" \
      --project "$GCP_PROJECT_ID" \
      --region "$GCP_REGION" \
      --update-secrets="MPLACAS_OPERATIONS_API_KEY=${SECRET_OPERATIONS_KEY}:${previous_version}" \
      --quiet >/dev/null || warn "service rollback failed and requires manual intervention"
    gcloud secrets versions disable "$new_version" \
      --secret "$SECRET_OPERATIONS_KEY" \
      --project "$GCP_PROJECT_ID" \
      --quiet >/dev/null || warn "new secret version could not be disabled"
  fi
  clear_sensitive_values
  exit "$failure_status"
}
trap rollback_rotation ERR
trap clear_sensitive_values EXIT

new_version="$(
  printf '%s' "$new_key" | gcloud secrets versions add "$SECRET_OPERATIONS_KEY" \
    --project "$GCP_PROJECT_ID" \
    --data-file=- \
    --format='value(name.basename())' \
    --quiet
)"
[[ "$new_version" =~ ^[0-9]+$ ]] || die "new secret version was not returned"

gcloud run services update "$GCP_SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --update-secrets="MPLACAS_OPERATIONS_API_KEY=${SECRET_OPERATIONS_KEY}:latest" \
  --quiet >/dev/null

service_url="$(cloud_run_service_url)"
[[ -n "$service_url" ]] || die "service URL not found"

health_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${service_url}/health")"
ready_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${service_url}/ready")"
new_key_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --header "X-API-Key: ${new_key}" "${service_url}/operations/status")"
previous_key_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --header "X-API-Key: ${previous_key}" "${service_url}/operations/status")"

[[ "$health_status" == "200" ]] || die "health validation failed after rotation"
[[ "$ready_status" == "200" ]] || die "readiness validation failed after rotation"
[[ "$new_key_status" == "200" ]] || die "new operations key was not accepted"
[[ "$previous_key_status" == "401" ]] || die "previous operations key is still accepted"

for job_name in \
  "${GCP_OPERATIONAL_JOB_PREFIX}-smoke" \
  "${GCP_OPERATIONAL_JOB_PREFIX}-operational-watchdog"; do
  gcloud run jobs execute "$job_name" \
    --project "$GCP_PROJECT_ID" \
    --region "$GCP_REGION" \
    --wait \
    --quiet >/dev/null
done

rotation_committed="true"
trap - ERR
log "operations key rotation approved"
log "previous version retained for rollback: ${previous_version}"
log "active version: ${new_version}"
log "service URL: ${service_url}"
