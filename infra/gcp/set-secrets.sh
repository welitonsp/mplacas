#!/usr/bin/env bash
set -Eeuo pipefail

# Uso: bash infra/gcp/set-secrets.sh <subcomando> [--rotate-jwt]
# Subcomandos: database-runtime, database-migration, operations-key, jwt, all.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

_read_secret_value() {
  local label="$1"
  local value
  if [[ -t 0 ]]; then
    printf 'Informe o valor de %s (sem eco): ' "$label" >&2
    IFS= read -r -s value
    printf '\n' >&2
  else
    IFS= read -r value
  fi
  [[ -n "$value" ]] || die "valor vazio rejeitado para ${label}"
  printf '%s' "$value"
}

_ensure_secret_exists() {
  local secret_name="$1"
  if gcloud secrets describe "$secret_name" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    log "secret já existe: ${secret_name}"
    return
  fi
  gcloud secrets create "$secret_name" \
    --replication-policy="automatic" \
    --project "$GCP_PROJECT_ID"
  log "secret criado: ${secret_name}"
}

_grant_runtime_secret_access() {
  local secret_name="$1"
  gcloud secrets add-iam-policy-binding "$secret_name" \
    --member="serviceAccount:$(runtime_service_account_email)" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$GCP_PROJECT_ID" \
    >/dev/null
}

_confirm_secret_version_enabled() {
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
    "nova versão ${version} de ${secret_name} não está ENABLED"
}

_disable_old_enabled_versions() {
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
    log "versão antiga desabilitada: ${secret_name}@${version}"
  done < <(list_enabled_secret_versions "$secret_name")
}

_assert_single_enabled_version() {
  local secret_name="$1"
  local enabled_count
  enabled_count="$(count_enabled_secret_versions "$secret_name")"
  [[ "$enabled_count" == "1" ]] || die \
    "${secret_name} deve ter exatamente uma versão ENABLED; encontrado: ${enabled_count}"
}

_add_secret_version_interactive() {
  local secret_name="$1"
  local label="$2"
  local endpoint_kind="${3:-}"
  local tmpfile
  local new_version

  tmpfile="$(mktemp)"
  chmod 600 "$tmpfile"
  trap 'rm -f -- "${tmpfile}"' EXIT
  _read_secret_value "$label" >"$tmpfile"

  if [[ -n "$endpoint_kind" ]]; then
    validate_database_endpoint_file "$tmpfile" "$endpoint_kind"
    log "endpoint ${endpoint_kind} validado sem exibir a connection string"
  fi

  new_version="$(
    gcloud secrets versions add "$secret_name" \
      --data-file="$tmpfile" \
      --project "$GCP_PROJECT_ID" \
      --format='value(name.basename())'
  )"

  rm -f -- "$tmpfile"
  trap - EXIT
  [[ "$new_version" =~ ^[0-9]+$ ]] || die \
    "número de versão não retornado para ${secret_name}"
  _confirm_secret_version_enabled "$secret_name" "$new_version"
  _disable_old_enabled_versions "$secret_name" "$new_version"
  _assert_single_enabled_version "$secret_name"
  log "nova versão habilitada: ${secret_name}"
}

_set_database_runtime() {
  _ensure_secret_exists "$SECRET_DATABASE_URL"
  _grant_runtime_secret_access "$SECRET_DATABASE_URL"
  _add_secret_version_interactive \
    "$SECRET_DATABASE_URL" \
    "MPLACAS_DATABASE_URL (pooled/runtime)" \
    "runtime"
}

_set_database_migration() {
  _ensure_secret_exists "$SECRET_MIGRATION_DATABASE_URL"
  _grant_runtime_secret_access "$SECRET_MIGRATION_DATABASE_URL"
  _add_secret_version_interactive \
    "$SECRET_MIGRATION_DATABASE_URL" \
    "MPLACAS_MIGRATION_DATABASE_URL (direto/não-pooled)" \
    "migration"
}

_set_operations_key() {
  _ensure_secret_exists "$SECRET_OPERATIONS_KEY"
  _grant_runtime_secret_access "$SECRET_OPERATIONS_KEY"
  _add_secret_version_interactive "$SECRET_OPERATIONS_KEY" "MPLACAS_OPERATIONS_API_KEY"
}

_set_jwt() {
  local rotate_flag="${1:-}"
  local existing_count
  local tmpfile
  local new_version

  _ensure_secret_exists "$SECRET_JWT"
  _grant_runtime_secret_access "$SECRET_JWT"
  existing_count="$(count_enabled_secret_versions "$SECRET_JWT")"

  if [[ "$existing_count" -ge 1 && "$rotate_flag" != "--rotate-jwt" ]]; then
    warn "${SECRET_JWT} já possui versão ENABLED; nada foi modificado."
    warn "Para rotacionar: $0 jwt --rotate-jwt"
    return 0
  fi

  if [[ "$existing_count" -ge 1 ]]; then
    log "ATENÇÃO: a rotação invalida todos os tokens JWT ativos."
    confirm_exact \
      "CONFIRMAR" \
      "Digite CONFIRMAR para rotacionar ${SECRET_JWT}:"
  fi

  tmpfile="$(mktemp)"
  chmod 600 "$tmpfile"
  trap 'rm -f -- "${tmpfile}"' EXIT
  openssl rand -base64 32 >"$tmpfile"
  new_version="$(
    gcloud secrets versions add "$SECRET_JWT" \
      --data-file="$tmpfile" \
      --project "$GCP_PROJECT_ID" \
      --format='value(name.basename())'
  )"
  rm -f -- "$tmpfile"
  trap - EXIT

  [[ "$new_version" =~ ^[0-9]+$ ]] || die \
    "número de versão não retornado para ${SECRET_JWT}"
  _confirm_secret_version_enabled "$SECRET_JWT" "$new_version"
  _disable_old_enabled_versions "$SECRET_JWT" "$new_version"
  _assert_single_enabled_version "$SECRET_JWT"
  log "novo JWT secret habilitado; valor nunca foi impresso"
}

_set_all() {
  _set_database_runtime
  _set_database_migration
  _set_operations_key
  _set_jwt ""
}

load_config
require_gcloud
require_authenticated_gcloud
require_command openssl
configure_gcloud_project
validate_billing_enabled
ensure_runtime_service_account

cmd="${1:-}"
case "$cmd" in
  database-runtime) _set_database_runtime ;;
  database-migration) _set_database_migration ;;
  operations-key) _set_operations_key ;;
  jwt) _set_jwt "${2:-}" ;;
  all) _set_all ;;
  *)
    printf 'Uso: %s {database-runtime|database-migration|operations-key|jwt [--rotate-jwt]|all}\n' "$0" >&2
    exit 1
    ;;
esac
