#!/usr/bin/env bash
set -Eeuo pipefail
# set-secrets.sh — granular secret management for Mplacas GCP deployment.
#
# Uso: bash infra/gcp/set-secrets.sh <subcomando> [--rotate-jwt]
#
# Subcomandos:
#   database-runtime   — cria/atualiza mplacas-database-url (pooled, runtime)
#   database-migration — cria/atualiza mplacas-migration-database-url (direto, migracoes)
#   operations-key     — cria/atualiza mplacas-operations-key
#   jwt [--rotate-jwt] — cria mplacas-jwt-secret (rotacao exige --rotate-jwt + confirmacao)
#   all                — executa database-runtime, database-migration, operations-key e jwt
#
# Regras de seguranca:
#   - Nunca imprime valores de segredos.
#   - Le valores via read -rs (sem eco) ou arquivo temporario com mktemp + rm.
#   - jwt sem --rotate-jwt: cria somente se nao existir; se ja existir, avisa e sai.
#   - jwt --rotate-jwt: exige digitacao de CONFIRMAR antes de prosseguir.
#   - Cada subcomando afeta apenas a sua secret.
#   - Apos criar/atualizar, desabilita versoes antigas (preserva exatamente uma ENABLED).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

# ---------------------------------------------------------------------------
# Funções auxiliares locais
# ---------------------------------------------------------------------------

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

# Cria uma nova versão de um secret lendo o valor via stdin (sem eco).
# O valor é escrito em arquivo temporário e enviado via --data-file para evitar
# que apareça em `set -x`, shell history ou no process list.
_add_secret_version_interactive() {
  local secret_name="$1"
  local label="$2"
  local tmpfile
  local new_version

  tmpfile="$(mktemp)"
  # Garante remoção segura do arquivo temporário ao sair, mesmo em erro.
  trap 'rm -f -- "${tmpfile}"' EXIT

  _read_secret_value "$label" > "$tmpfile"

  log "Criando nova versão do secret ${secret_name}..."
  new_version="$(
    gcloud secrets versions add "$secret_name" \
      --data-file="$tmpfile" \
      --project "$GCP_PROJECT_ID" \
      --format='value(name.basename())'
  )"

  # Limpa o arquivo antes de remover (best-effort; rm -f no trap é o fallback).
  rm -f -- "$tmpfile"
  trap - EXIT

  [[ "$new_version" =~ ^[0-9]+$ ]] || die \
    "número de versão não retornado para ${secret_name}"

  _confirm_secret_version_enabled "$secret_name" "$new_version"
  _disable_old_enabled_versions "$secret_name" "$new_version"
  _assert_single_enabled_version "$secret_name"
  log "nova versão habilitada: ${secret_name}"
}

# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------

_set_database_runtime() {
  log "==> Configurando secret de banco de dados (runtime/pooled): ${SECRET_DATABASE_URL}"
  _ensure_secret_exists "$SECRET_DATABASE_URL"
  _grant_runtime_secret_access "$SECRET_DATABASE_URL"
  _add_secret_version_interactive "$SECRET_DATABASE_URL" "MPLACAS_DATABASE_URL (pooled/runtime)"
  log "Secret ${SECRET_DATABASE_URL} atualizado com sucesso."
}

_set_database_migration() {
  log "==> Configurando secret de banco de dados (migration/direto): ${SECRET_MIGRATION_DATABASE_URL}"
  _ensure_secret_exists "$SECRET_MIGRATION_DATABASE_URL"
  _grant_runtime_secret_access "$SECRET_MIGRATION_DATABASE_URL"
  _add_secret_version_interactive "$SECRET_MIGRATION_DATABASE_URL" "MPLACAS_MIGRATION_DATABASE_URL (direto/não-pooled)"
  log "Secret ${SECRET_MIGRATION_DATABASE_URL} atualizado com sucesso."
}

_set_operations_key() {
  log "==> Configurando secret de chave operacional: ${SECRET_OPERATIONS_KEY}"
  _ensure_secret_exists "$SECRET_OPERATIONS_KEY"
  _grant_runtime_secret_access "$SECRET_OPERATIONS_KEY"
  _add_secret_version_interactive "$SECRET_OPERATIONS_KEY" "MPLACAS_OPERATIONS_KEY"
  log "Secret ${SECRET_OPERATIONS_KEY} atualizado com sucesso."
}

_set_jwt() {
  local rotate_flag="${1:-}"
  local secret_name="$SECRET_JWT"

  log "==> Configurando secret JWT: ${secret_name}"
  _ensure_secret_exists "$secret_name"
  _grant_runtime_secret_access "$secret_name"

  # Verifica se já existe alguma versão ENABLED.
  local existing_count
  existing_count="$(count_enabled_secret_versions "$secret_name")"

  if [[ "$existing_count" -ge "1" ]]; then
    if [[ "$rotate_flag" != "--rotate-jwt" ]]; then
      warn "${secret_name} já possui ${existing_count} versão(ões) ENABLED."
      warn "Para rotacionar, execute: $0 jwt --rotate-jwt"
      warn "O secret NÃO foi modificado."
      return 0
    fi

    # Rotação exige confirmação explícita.
    log "ATENÇÃO: rotação do JWT secret invalida todos os tokens ativos."
    confirm_exact \
      "CONFIRMAR" \
      "Digite CONFIRMAR para rotacionar ${secret_name} (invalida tokens existentes):"
  fi

  # Gera e armazena 32 bytes aleatórios via arquivo temporário.
  # O valor nunca é armazenado em variável de shell nem impresso.
  local tmpfile
  local new_version

  tmpfile="$(mktemp)"
  trap 'rm -f -- "${tmpfile}"' EXIT

  log "Gerando novo JWT secret com openssl rand..."
  openssl rand -base64 32 > "$tmpfile"

  log "Criando nova versão do secret ${secret_name}..."
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
  log "novo JWT secret habilitado: ${secret_name} (valor nunca foi impresso)"
}

_set_all() {
  log "==> Executando todos os subcomandos em sequência..."
  _set_database_runtime
  _set_database_migration
  _set_operations_key
  _set_jwt ""
  log "==> Todos os secrets configurados com sucesso."
}

# ---------------------------------------------------------------------------
# Inicialização comum
# ---------------------------------------------------------------------------

load_config
require_gcloud
require_authenticated_gcloud
configure_gcloud_project
validate_billing_enabled
ensure_runtime_service_account

# ---------------------------------------------------------------------------
# Dispatch de subcomandos
# ---------------------------------------------------------------------------

cmd="${1:-}"
case "$cmd" in
  database-runtime)   _set_database_runtime ;;
  database-migration) _set_database_migration ;;
  operations-key)     _set_operations_key ;;
  jwt)                _set_jwt "${2:-}" ;;
  all)                _set_all ;;
  *)
    printf 'Uso: %s {database-runtime|database-migration|operations-key|jwt [--rotate-jwt]|all}\n' "$0" >&2
    exit 1
    ;;
esac
