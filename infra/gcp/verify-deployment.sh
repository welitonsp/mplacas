#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

fetch_and_validate() {
  local url="$1"
  local expected_status="$2"
  local output_file="$3"
  local http_status

  http_status="$(
    curl --fail --silent --show-error \
      --connect-timeout 5 \
      --max-time 20 \
      --output "$output_file" \
      --write-out '%{http_code}' \
      "$url"
  )"
  [[ "$http_status" == "$expected_status" ]] || die \
    "unexpected HTTP status for ${url}"
  assert_no_sensitive_response "$output_file"
}

validate_json_status() {
  local file="$1"
  local expected="$2"

  python3 - "$file" "$expected" <<'PY'
import json
import sys

path, expected = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
if payload.get("status") != expected:
    raise SystemExit(f"unexpected status: {payload!r}")
PY
}

load_config
require_gcloud
require_authenticated_gcloud
require_curl
require_python
configure_gcloud_project

SERVICE_URL="$(cloud_run_service_url)"
[[ -n "$SERVICE_URL" ]] || die "service URL not found"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fetch_and_validate "${SERVICE_URL}/health" "200" "${TMP_DIR}/health.json"
validate_json_status "${TMP_DIR}/health.json" "ok"

fetch_and_validate "${SERVICE_URL}/ready" "200" "${TMP_DIR}/ready.json"
validate_json_status "${TMP_DIR}/ready.json" "ready"

fetch_and_validate "${SERVICE_URL}/dashboard" "200" "${TMP_DIR}/dashboard.html"
validate_cloud_run_limits

log "deployment verification completed"
log "service URL: ${SERVICE_URL}"
