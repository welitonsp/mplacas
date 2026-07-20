#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

read_secret_value() {
  local label="$1"
  local value

  if [[ -t 0 ]]; then
    printf 'Enter %s value: ' "$label" >&2
    IFS= read -r -s value
    printf '\n' >&2
  else
    IFS= read -r value
  fi

  [[ -n "$value" ]] || die "empty secret value rejected"
  printf '%s' "$value"
}

ensure_secret_exists() {
  local secret_name="$1"

  if gcloud secrets describe "$secret_name" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    log "secret exists: ${secret_name}"
    return
  fi

  gcloud secrets create "$secret_name" \
    --replication-policy="automatic" \
    --project "$GCP_PROJECT_ID"
  log "secret created: ${secret_name}"
}

grant_runtime_secret_access() {
  local secret_name="$1"

  gcloud secrets add-iam-policy-binding "$secret_name" \
    --member="serviceAccount:$(runtime_service_account_email)" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$GCP_PROJECT_ID" \
    >/dev/null
}

confirm_secret_version_enabled() {
  local secret_name="$1"
  local version="$2"
  local state

  state="$(
    gcloud secrets versions describe "$version" \
      --secret "$secret_name" \
      --format='value(state)' \
      --project "$GCP_PROJECT_ID"
  )"
  [[ "$state" == "ENABLED" ]] || die \
    "new ${secret_name} version is not ENABLED"
}

disable_old_enabled_versions() {
  local secret_name="$1"
  local keep_version="$2"
  local version

  while IFS= read -r version; do
    [[ -n "$version" ]] || continue
    [[ "$version" == "$keep_version" ]] && continue

    gcloud secrets versions disable "$version" \
      --secret "$secret_name" \
      --quiet \
      --project "$GCP_PROJECT_ID" \
      >/dev/null
  done < <(list_enabled_secret_versions "$secret_name")
}

assert_single_enabled_secret_version() {
  local secret_name="$1"
  local enabled_count

  enabled_count="$(count_enabled_secret_versions "$secret_name")"
  [[ "$enabled_count" == "1" ]] || die \
    "${secret_name} must have exactly one ENABLED version"
}

add_secret_version() {
  local secret_name="$1"
  local label="$2"
  local new_version

  new_version="$(
    read_secret_value "$label" |
      gcloud secrets versions add "$secret_name" \
        --data-file=- \
        --project "$GCP_PROJECT_ID" \
        --format='value(name.basename())'
  )"

  [[ "$new_version" =~ ^[0-9]+$ ]] || die \
    "new secret version number was not returned for ${secret_name}"

  confirm_secret_version_enabled "$secret_name" "$new_version"
  disable_old_enabled_versions "$secret_name" "$new_version"
  assert_single_enabled_secret_version "$secret_name"
  log "new secret version enabled: ${secret_name}"
}

load_config
require_gcloud
require_authenticated_gcloud
configure_gcloud_project
validate_billing_enabled
ensure_runtime_service_account

ensure_secret_exists "mplacas-database-url"
grant_runtime_secret_access "mplacas-database-url"
add_secret_version "mplacas-database-url" "MPLACAS_DATABASE_URL"

ensure_secret_exists "mplacas-operations-api-key"
grant_runtime_secret_access "mplacas-operations-api-key"
add_secret_version "mplacas-operations-api-key" "MPLACAS_OPERATIONS_API_KEY"

# --- JWT secret ---
# 32 cryptographically random bytes (base64-encoded ~43 chars).
# Generated entirely inside this script; the value is never printed.
# The runtime Cloud Run service reads it as MPLACAS_JWT_SECRET via Secret Manager.
provision_jwt_secret() {
  local secret_name="mplacas-jwt-secret"
  local new_version

  ensure_secret_exists "$secret_name"
  grant_runtime_secret_access "$secret_name"

  # Generate and pipe directly to Secret Manager — value never stored in a variable
  # that could appear in `set -x` output or shell history.
  new_version="$(
    printf '%s' "$(openssl rand -base64 32)" |
      gcloud secrets versions add "$secret_name" \
        --data-file=- \
        --project "$GCP_PROJECT_ID" \
        --format='value(name.basename())'
  )"

  [[ "$new_version" =~ ^[0-9]+$ ]] || die \
    "new secret version number was not returned for ${secret_name}"

  confirm_secret_version_enabled "$secret_name" "$new_version"
  disable_old_enabled_versions "$secret_name" "$new_version"
  assert_single_enabled_secret_version "$secret_name"
  log "new JWT secret version enabled: ${secret_name} (value was never printed)"
}

provision_jwt_secret

log "secret metadata updated; secret values were never printed"
