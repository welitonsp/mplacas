#!/usr/bin/env bash
set -Eeuo pipefail

# The readonly arrays below are the public API consumed by scripts that source this library.
readonly MPLACAS_ALLOWED_REGION="us-central1"
# shellcheck disable=SC2034
readonly MPLACAS_REQUIRED_APIS=(
  "run.googleapis.com"
  "cloudbuild.googleapis.com"
  "artifactregistry.googleapis.com"
  "secretmanager.googleapis.com"
  "iam.googleapis.com"
  "cloudtrace.googleapis.com"
  "monitoring.googleapis.com"
)
# shellcheck disable=SC2034
readonly MPLACAS_SECRET_NAMES=(
  "mplacas-database-url"
  "mplacas-operations-api-key"
  "mplacas-jwt-secret"
)

: "${GCP_PROJECT_ID:=}"
: "${GCP_REGION:=}"
: "${GCP_SERVICE_NAME:=}"
: "${GCP_MIGRATION_JOB_NAME:=}"
: "${GCP_RUNTIME_SERVICE_ACCOUNT:=}"
: "${GCP_MIN_INSTANCES:=}"
: "${GCP_MAX_INSTANCES:=}"
: "${GCP_CPU:=}"
: "${GCP_MEMORY:=}"
: "${GCP_CONCURRENCY:=}"
: "${GCP_REQUEST_TIMEOUT:=}"
: "${MPLACAS_TIMEZONE:=}"
: "${MPLACAS_CORS_ALLOWED_ORIGINS:=}"

log() {
  printf '[mplacas:gcp] %s\n' "$*"
}

warn() {
  printf '[mplacas:gcp] warning: %s\n' "$*" >&2
}

die() {
  printf '[mplacas:gcp] error: %s\n' "$*" >&2
  exit 1
}

repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "${script_dir}/../.." && pwd
}

config_file() {
  local root
  root="$(repo_root)"
  printf '%s\n' "${MPLACAS_GCP_CONFIG_FILE:-${root}/infra/gcp/config.env}"
}

load_config() {
  local file
  file="$(config_file)"
  [[ -f "$file" ]] || die \
    "config file not found; copy infra/gcp/config.example.env to infra/gcp/config.env"

  # shellcheck source=/dev/null
  source "$file"
  validate_config
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || die "${command_name} is required"
}

require_gcloud() {
  require_command gcloud
}

require_curl() {
  require_command curl
}

require_python() {
  require_command python3
}

require_authenticated_gcloud() {
  local account
  account="$(
    gcloud auth list \
      --filter='status:ACTIVE' \
      --format='value(account)' \
      --limit=1
  )"
  [[ -n "$account" ]] || die \
    "no active gcloud account; run gcloud auth login in Google Cloud Shell"
  log "active gcloud account detected"
}

configure_gcloud_project() {
  require_gcloud
  gcloud config set project "$GCP_PROJECT_ID" >/dev/null
  gcloud config set run/region "$GCP_REGION" >/dev/null
}

validate_billing_enabled() {
  local enabled
  enabled="$(
    gcloud billing projects describe "$GCP_PROJECT_ID" \
      --format='value(billingEnabled)'
  )"
  [[ "$enabled" == "True" ]] || die "billing must be enabled before deployment"
}

validate_config() {
  require_value "GCP_PROJECT_ID" "${GCP_PROJECT_ID:-}"
  require_project_id "$GCP_PROJECT_ID"
  require_region "${GCP_REGION:-}"
  require_resource_name "GCP_SERVICE_NAME" "${GCP_SERVICE_NAME:-}"
  require_resource_name "GCP_MIGRATION_JOB_NAME" "${GCP_MIGRATION_JOB_NAME:-}"
  require_resource_name \
    "GCP_RUNTIME_SERVICE_ACCOUNT" \
    "${GCP_RUNTIME_SERVICE_ACCOUNT:-}"
  require_integer "GCP_MIN_INSTANCES" "${GCP_MIN_INSTANCES:-}"
  require_integer "GCP_MAX_INSTANCES" "${GCP_MAX_INSTANCES:-}"
  require_integer "GCP_CPU" "${GCP_CPU:-}"
  require_integer "GCP_CONCURRENCY" "${GCP_CONCURRENCY:-}"
  require_integer "GCP_REQUEST_TIMEOUT" "${GCP_REQUEST_TIMEOUT:-}"

  [[ "${GCP_MIN_INSTANCES:-}" == "0" ]] || die "GCP_MIN_INSTANCES must be 0"
  [[ "${GCP_MAX_INSTANCES:-}" == "1" ]] || die "GCP_MAX_INSTANCES must be 1"
  [[ "${GCP_CPU:-}" == "1" ]] || die "GCP_CPU must be 1"
  [[ "${GCP_MEMORY:-}" == "512Mi" ]] || die "GCP_MEMORY must be 512Mi"
  (( GCP_CONCURRENCY >= 1 && GCP_CONCURRENCY <= 80 )) || die "invalid concurrency"
  (( GCP_REQUEST_TIMEOUT >= 1 && GCP_REQUEST_TIMEOUT <= 300 )) || die "invalid timeout"
  [[ "${MPLACAS_TIMEZONE:-}" == "America/Sao_Paulo" ]] || die "unsupported timezone"
}

require_value() {
  local name="$1"
  local value="$2"
  [[ -n "$value" ]] || die "${name} is required"
}

require_project_id() {
  local value="$1"
  [[ "$value" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || die "invalid project id"
}

require_region() {
  local value="$1"
  [[ "$value" == "$MPLACAS_ALLOWED_REGION" ]] || die \
    "region must be ${MPLACAS_ALLOWED_REGION}"
}

require_resource_name() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[a-z][a-z0-9-]{0,61}[a-z0-9]$ ]] || die "invalid ${name}"
}

require_integer() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "${name} must be an integer"
}

confirm_exact() {
  local expected="$1"
  local prompt="$2"
  local typed
  printf '%s\n> ' "$prompt" >&2
  IFS= read -r typed
  [[ "$typed" == "$expected" ]] || die "confirmation did not match"
}

runtime_service_account_email() {
  printf '%s@%s.iam.gserviceaccount.com\n' \
    "$GCP_RUNTIME_SERVICE_ACCOUNT" \
    "$GCP_PROJECT_ID"
}

ensure_runtime_service_account() {
  local email
  email="$(runtime_service_account_email)"

  if gcloud iam service-accounts describe "$email" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    log "runtime service account already exists"
    return
  fi

  gcloud iam service-accounts create "$GCP_RUNTIME_SERVICE_ACCOUNT" \
    --display-name="Mplacas Cloud Run runtime" \
    --description="Least-privilege runtime identity for Mplacas Cloud Run" \
    --project "$GCP_PROJECT_ID"
  log "runtime service account created"
}

ensure_runtime_trace_access() {
  local member
  member="serviceAccount:$(runtime_service_account_email)"
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="$member" \
    --role="roles/cloudtrace.agent" \
    --condition=None \
    --quiet >/dev/null
  log "runtime service account can write Cloud Trace spans"
}

ensure_runtime_metrics_access() {
  local member
  member="serviceAccount:$(runtime_service_account_email)"
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="$member" \
    --role="roles/monitoring.metricWriter" \
    --condition=None \
    --quiet >/dev/null
  log "runtime service account can write Cloud Monitoring metrics"
}

api_enabled() {
  local api="$1"
  local enabled
  enabled="$(
    gcloud services list \
      --enabled \
      --filter="config.name=${api}" \
      --format='value(config.name)' \
      --project "$GCP_PROJECT_ID"
  )"
  [[ "$enabled" == "$api" ]]
}

cloud_run_service_url() {
  gcloud run services describe "$GCP_SERVICE_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --format='value(status.url)'
}

cloud_run_service_image() {
  gcloud run services describe "$GCP_SERVICE_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --format='value(spec.template.spec.containers[0].image)'
}

list_enabled_secret_versions() {
  local secret_name="$1"
  gcloud secrets versions list "$secret_name" \
    --filter='state=ENABLED' \
    --format='value(name.basename())' \
    --project "$GCP_PROJECT_ID"
}

count_enabled_secret_versions() {
  local secret_name="$1"
  local count=0
  local version

  while IFS= read -r version; do
    [[ -n "$version" ]] || continue
    ((count += 1))
  done < <(list_enabled_secret_versions "$secret_name")

  printf '%s\n' "$count"
}

assert_no_sensitive_response() {
  local file="$1"
  if grep -Eiq \
    'postgres(ql)?(\+asyncpg)?://|password|secret|token|DATABASE_URL|OPERATIONS_API_KEY' \
    "$file"; then
    die "response contains sensitive-looking content"
  fi
}

validate_cloud_run_limits() {
  local description_file
  description_file="$(mktemp)"

  gcloud run services describe "$GCP_SERVICE_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --format=json >"$description_file"

  python3 - "$description_file" \
    "$GCP_MIN_INSTANCES" \
    "$GCP_MAX_INSTANCES" \
    "$GCP_CPU" \
    "$GCP_MEMORY" \
    "$(runtime_service_account_email)" <<'PY'
import json
import sys

(
    path,
    expected_min,
    expected_max,
    expected_cpu,
    expected_memory,
    expected_service_account,
) = sys.argv[1:]

with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

try:
    template = payload["spec"]["template"]
    annotations = template["metadata"]["annotations"]
    container = template["spec"]["containers"][0]
    values = {
        "min_instances": annotations["autoscaling.knative.dev/minScale"],
        "max_instances": annotations["autoscaling.knative.dev/maxScale"],
        "service_account": template["spec"]["serviceAccountName"],
        "cpu": container["resources"]["limits"]["cpu"],
        "memory": container["resources"]["limits"]["memory"],
    }
except (KeyError, IndexError, TypeError) as exc:
    raise SystemExit(f"missing Cloud Run revision field: {exc}") from exc

cpu = str(values["cpu"])
normalized_cpu = "1" if cpu == "1000m" else cpu
expected = {
    "min_instances": expected_min,
    "max_instances": expected_max,
    "service_account": expected_service_account,
    "cpu": expected_cpu,
    "memory": expected_memory,
}
actual = {**values, "cpu": normalized_cpu}

if actual != expected:
    raise SystemExit(f"Cloud Run guardrail mismatch: actual={actual!r} expected={expected!r}")
PY

  rm -f "$description_file"
}
