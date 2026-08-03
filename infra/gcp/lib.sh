#!/usr/bin/env bash
set -Eeuo pipefail

readonly MPLACAS_ALLOWED_REGION="us-central1"
readonly SECRET_DATABASE_URL="mplacas-database-url"
readonly SECRET_MIGRATION_DATABASE_URL="mplacas-migration-database-url"
readonly SECRET_OPERATIONS_KEY="mplacas-operations-api-key"
readonly SECRET_JWT="mplacas-jwt-secret"
readonly SECRET_TELEGRAM_BOT_TOKEN="mplacas-telegram-bot-token"
readonly SECRET_TELEGRAM_WEBHOOK_SECRET="mplacas-telegram-webhook-secret"
readonly SECRET_NEP_ACCOUNT="mplacas-nep-account"
readonly SECRET_NEP_PASSWORD="mplacas-nep-password"

# Public arrays consumed by scripts that source this library.
# shellcheck disable=SC2034
readonly MPLACAS_REQUIRED_APIS=(
  "run.googleapis.com"
  "cloudbuild.googleapis.com"
  "artifactregistry.googleapis.com"
  "secretmanager.googleapis.com"
  "iam.googleapis.com"
  "cloudtrace.googleapis.com"
  "monitoring.googleapis.com"
  "cloudscheduler.googleapis.com"
)
# shellcheck disable=SC2034
readonly MPLACAS_SECRET_NAMES=(
  "$SECRET_DATABASE_URL"
  "$SECRET_MIGRATION_DATABASE_URL"
  "$SECRET_OPERATIONS_KEY"
  "$SECRET_JWT"
  "$SECRET_TELEGRAM_BOT_TOKEN"
  "$SECRET_TELEGRAM_WEBHOOK_SECRET"
  "$SECRET_NEP_ACCOUNT"
  "$SECRET_NEP_PASSWORD"
)

# Single source of truth for every Cloud Scheduler job this project is
# expected to own. audit-costs.sh treats anything named `~mplacas` that is
# NOT in this list as a prohibited/unexpected resource. Keep this in sync
# with provision-operations.sh (OPERATIONAL_COMMANDS) and
# provision-cost-audit.sh whenever a job is added or removed.
# shellcheck disable=SC2034
readonly MPLACAS_EXPECTED_SCHEDULER_JOBS=(
  "mplacas-collect"
  "mplacas-daily-pipeline"
  "mplacas-dispatch-outbox"
  "mplacas-drain-collection"
  "mplacas-drain-report-exports"
  "mplacas-daily-digest"
  "mplacas-operational-watchdog"
  "mplacas-retention"
  "mplacas-cost-audit"
  # TEMPORARY — added for the operational-watchdog absence drill, see
  # docs/RUNBOOK_WATCHDOG_DRILL.md and infra/gcp/drill/. Remove this entry
  # once infra/gcp/drill/teardown-watchdog-drill.sh has been run and the
  # drill Scheduler job/Cloud Run Job/alert policy no longer exist — leaving
  # it here after teardown would let a stale resource silently pass
  # audit-costs.sh's guardrail.
  "mplacas-watchdog-drill"
)

: "${GCP_PROJECT_ID:=}"
: "${GCP_REGION:=}"
: "${GCP_SERVICE_NAME:=}"
: "${GCP_MIGRATION_JOB_NAME:=}"
: "${GCP_RUNTIME_SERVICE_ACCOUNT:=}"
: "${GCP_SCHEDULER_SERVICE_ACCOUNT:=mplacas-scheduler}"
: "${MPLACAS_AUDITOR_SERVICE_ACCOUNT:=mplacas-auditor}"
: "${GCP_OPERATIONAL_JOB_PREFIX:=mplacas}"
: "${GCP_MONITORING_NOTIFICATION_CHANNELS:=}"
: "${GCP_MIN_INSTANCES:=}"
: "${GCP_MAX_INSTANCES:=}"
: "${GCP_CPU:=}"
: "${GCP_MEMORY:=}"
: "${GCP_CONCURRENCY:=}"
: "${GCP_REQUEST_TIMEOUT:=}"
: "${MPLACAS_TIMEZONE:=}"
: "${MPLACAS_CORS_ALLOWED_ORIGINS:=}"
: "${MPLACAS_DASHBOARD_URL:=https://mplacas-frontend.pages.dev/dashboard}"
: "${MPLACAS_TELEGRAM_ALERT_CHAT_ID:=}"
: "${MPLACAS_CLOUD_JOB_PLANT_NAME:=}"
: "${MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH:=}"
: "${MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH:=}"

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

  if [[ ! -f "$file" ]]; then
    # Scheduled/automated runs (e.g. the Cloud Run Job container for
    # audit-costs.sh) have no config.env on disk — config.env is
    # deliberately never committed. MPLACAS_CONFIG_FROM_ENV=1 opts into
    # sourcing configuration straight from the process environment instead;
    # validate_config() below still enforces the same rules either way.
    [[ "${MPLACAS_CONFIG_FROM_ENV:-}" == "1" ]] || die \
      "config file not found; copy infra/gcp/config.example.env to infra/gcp/config.env"
    validate_config
    return
  fi

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

scheduler_job_is_expected() {
  local job_name="$1"
  local expected
  for expected in "${MPLACAS_EXPECTED_SCHEDULER_JOBS[@]}"; do
    [[ "$job_name" == "$expected" ]] && return 0
  done
  return 1
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
  require_resource_name \
    "GCP_SCHEDULER_SERVICE_ACCOUNT" \
    "${GCP_SCHEDULER_SERVICE_ACCOUNT:-}"
  require_resource_name \
    "GCP_OPERATIONAL_JOB_PREFIX" \
    "${GCP_OPERATIONAL_JOB_PREFIX:-}"
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
  python3 - "${MPLACAS_DASHBOARD_URL:-}" <<'PY'
import sys
from urllib.parse import urlsplit

parsed = urlsplit(sys.argv[1])
if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
    raise SystemExit("MPLACAS_DASHBOARD_URL must be an absolute credential-free HTTPS URL")
if parsed.query or parsed.fragment:
    raise SystemExit("MPLACAS_DASHBOARD_URL cannot contain query or fragment")
PY
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

scheduler_service_account_email() {
  printf '%s@%s.iam.gserviceaccount.com\n' \
    "$GCP_SCHEDULER_SERVICE_ACCOUNT" \
    "$GCP_PROJECT_ID"
}

auditor_service_account_email() {
  printf '%s@%s.iam.gserviceaccount.com\n' \
    "$MPLACAS_AUDITOR_SERVICE_ACCOUNT" \
    "$GCP_PROJECT_ID"
}

ensure_scheduler_service_account() {
  local email
  email="$(scheduler_service_account_email)"

  if gcloud iam service-accounts describe "$email" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    log "scheduler service account already exists"
    return
  fi

  gcloud iam service-accounts create "$GCP_SCHEDULER_SERVICE_ACCOUNT" \
    --display-name="Mplacas Cloud Scheduler invoker" \
    --description="Dedicated identity that invokes Mplacas operational jobs" \
    --project "$GCP_PROJECT_ID"
  log "scheduler service account created"
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

ensure_auditor_service_account() {
  local email
  email="$(auditor_service_account_email)"

  if gcloud iam service-accounts describe "$email" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    log "auditor service account already exists"
    return
  fi

  gcloud iam service-accounts create "$MPLACAS_AUDITOR_SERVICE_ACCOUNT" \
    --display-name="Mplacas cost-audit read-only identity" \
    --description="Least-privilege identity for the automated audit-costs.sh Cloud Run Job; never holds secretAccessor or billing.viewer" \
    --project "$GCP_PROJECT_ID"
  log "auditor service account created"
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

validate_monitoring_notification_channels() {
  require_value \
    "GCP_MONITORING_NOTIFICATION_CHANNELS" \
    "${GCP_MONITORING_NOTIFICATION_CHANNELS:-}"
  python3 - "$GCP_PROJECT_ID" "$GCP_MONITORING_NOTIFICATION_CHANNELS" <<'PY'
import re
import sys

project_id, value = sys.argv[1:]
channels = value.split(",")
if any(not channel or channel != channel.strip() for channel in channels):
    raise SystemExit("notification channels must be a comma-separated list without blanks")
pattern = re.compile(
    rf"^projects/{re.escape(project_id)}/notificationChannels/[A-Za-z0-9_-]+$"
)
if any(not pattern.fullmatch(channel) for channel in channels):
    raise SystemExit("notification channel must be a full resource name in this project")
PY
}

render_monitoring_policy() {
  local template_file="$1"
  local output_file="$2"
  python3 - \
    "$template_file" \
    "$output_file" \
    "$GCP_REGION" \
    "$GCP_OPERATIONAL_JOB_PREFIX" <<'PY'
import json
import pathlib
import sys

template_path, output_path, region, prefix = sys.argv[1:]
payload = json.loads(pathlib.Path(template_path).read_text(encoding="utf-8"))
replacements = {
    "${GCP_REGION}": region,
    "${GCP_OPERATIONAL_JOB_PREFIX}": prefix,
}

def render(value):
    if isinstance(value, str):
        for source, target in replacements.items():
            value = value.replace(source, target)
        return value
    if isinstance(value, list):
        return [render(item) for item in value]
    if isinstance(value, dict):
        return {key: render(item) for key, item in value.items()}
    return value

pathlib.Path(output_path).write_text(
    json.dumps(render(payload), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

find_monitoring_policy() {
  local policy_id="$1"
  local list_file
  list_file="$(mktemp)"
  gcloud monitoring policies list \
    --project "$GCP_PROJECT_ID" \
    --format=json >"$list_file"
  python3 - "$list_file" "$policy_id" <<'PY'
import json
import pathlib
import sys

path, policy_id = sys.argv[1:]
policies = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
matches = [
    policy.get("name", "")
    for policy in policies
    if policy.get("userLabels", {}).get("mplacas_policy_id") == policy_id
]
if len(matches) > 1:
    raise SystemExit(f"duplicate managed monitoring policy: {policy_id}")
if matches:
    print(matches[0])
PY
  rm -f -- "$list_file"
}

upsert_monitoring_policy() {
  local policy_id="$1"
  local template_file="$2"
  local rendered_file
  local existing_name
  rendered_file="$(mktemp)"
  render_monitoring_policy "$template_file" "$rendered_file"
  existing_name="$(find_monitoring_policy "$policy_id")"
  if [[ -n "$existing_name" ]]; then
    gcloud monitoring policies update "$existing_name" \
      --project "$GCP_PROJECT_ID" \
      --policy-from-file "$rendered_file" \
      --set-notification-channels "$GCP_MONITORING_NOTIFICATION_CHANNELS" \
      --quiet >/dev/null
    log "monitoring policy updated: ${policy_id}"
  else
    gcloud monitoring policies create \
      --project "$GCP_PROJECT_ID" \
      --policy-from-file "$rendered_file" \
      --notification-channels "$GCP_MONITORING_NOTIFICATION_CHANNELS" \
      --quiet >/dev/null
    log "monitoring policy created: ${policy_id}"
  fi
  rm -f -- "$rendered_file"
}

verify_monitoring_policy() {
  local policy_id="$1"
  local policy_name
  local policy_file
  policy_name="$(find_monitoring_policy "$policy_id")"
  [[ -n "$policy_name" ]] || die "missing managed monitoring policy: ${policy_id}"
  policy_file="$(mktemp)"
  gcloud monitoring policies describe "$policy_name" \
    --project "$GCP_PROJECT_ID" \
    --format=json >"$policy_file"
  python3 - \
    "$policy_file" \
    "$policy_id" \
    "$GCP_MONITORING_NOTIFICATION_CHANNELS" <<'PY'
import json
import pathlib
import sys

path, policy_id, expected_channels_value = sys.argv[1:]
policy = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
if policy.get("userLabels", {}).get("mplacas_policy_id") != policy_id:
    raise SystemExit(f"monitoring policy identity mismatch: {policy_id}")
if policy.get("enabled") is not True:
    raise SystemExit(f"monitoring policy is disabled: {policy_id}")
expected_channels = set(expected_channels_value.split(","))
actual_channels = set(policy.get("notificationChannels", []))
if not expected_channels.issubset(actual_channels):
    raise SystemExit(
        f"monitoring policy channel mismatch: {policy_id}; "
        f"expected={sorted(expected_channels)!r} actual={sorted(actual_channels)!r}"
    )
PY
  rm -f -- "$policy_file"
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
        # Cloud Run omits the minScale annotation entirely when the value is
        # the default (0) — it is only written for a non-zero min-instances.
        "min_instances": annotations.get("autoscaling.knative.dev/minScale", "0"),
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

validate_cors_origins() {
  local origins="$1"
  python3 - "$origins" <<'PY'
import sys
from urllib.parse import urlsplit

value = sys.argv[1]
if not value:
    raise SystemExit("MPLACAS_CORS_ALLOWED_ORIGINS é obrigatório")

items = value.split(",")
if any(not item for item in items):
    raise SystemExit("lista CORS contém entrada vazia")

for origin in items:
    if origin != origin.strip() or any(char.isspace() for char in origin):
        raise SystemExit("origem CORS contém espaços")
    if "*" in origin:
        raise SystemExit("wildcard CORS não é permitido")
    parsed = urlsplit(origin)
    if parsed.scheme != "https":
        raise SystemExit("origem CORS deve usar https")
    if not parsed.hostname:
        raise SystemExit("origem CORS deve conter hostname")
    if parsed.username or parsed.password:
        raise SystemExit("origem CORS não pode conter credenciais")
    try:
        parsed.port
    except ValueError as exc:
        raise SystemExit("porta CORS inválida") from exc
    if parsed.path or parsed.query or parsed.fragment:
        raise SystemExit("origem CORS não pode conter caminho, query ou fragmento")

print(f"CORS origins validadas: {len(items)} origem(ns).")
PY
}

validate_database_endpoint_file() {
  local file="$1"
  local expected="$2"
  local library_dir
  library_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "${library_dir}/validate_database_url.py" "$file" "$expected"
}
