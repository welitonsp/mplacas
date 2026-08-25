#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/gcp/lib.sh
source "${SCRIPT_DIR}/lib.sh"

readonly OPERATIONAL_COMMANDS=(
  "collect"
  "daily-pipeline"
  "dispatch-outbox"
  "drain-collection"
  "drain-report-exports"
  "daily-digest"
  "operational-watchdog"
  "retention"
)

# Janela operacional única, 06:00-06:32 (America/Sao_Paulo).
#
# Por que uma janela em vez de horários espalhados
# ------------------------------------------------
# O Neon suspende o compute após 5 minutos sem conexão, e cobra por hora
# acordado — não por trabalho feito. O agendamento anterior tinha dois jobs em
# "*/5 * * * *", ou seja, uma conexão a cada 5 minutos contra um timeout de 5
# minutos: o banco nunca chegava a dormir. Ficava ligado 24 h/dia (~720 h/mês)
# para fazer poucos minutos de trabalho, e em 2026-08-21 isso esgotou a cota do
# plano, derrubou 100% dos jobs por 4 dias e quebrou o backup diário.
#
# Os intervalos abaixo são de 4 minutos: curtos o bastante para o banco não
# suspender no meio da janela (senão cada job vira um despertar novo), e longos
# o bastante para cada job terminar antes do próximo começar — as execuções
# medidas levavam 1-2 min de trabalho.
#
# Resultado: ~39 min acordado por dia (~20 h/mês) em vez de 720 h/mês.
#
# A ordem respeita a dependência real entre os jobs: coletar antes de calcular,
# calcular antes de despachar o alerta que o cálculo gera, e o watchdog por
# último, para conferir que o pipeline do dia de fato rodou.
declare -Ar OPERATIONAL_SCHEDULES=(
  [collect]="0 6 * * *"               # busca telemetria do fornecedor
  [drain-collection]="4 6 * * *"      # drena a fila de coleta
  [daily-pipeline]="8 6 * * *"        # calcula a análise do dia
  [dispatch-outbox]="12 6 * * *"      # envia os alertas que o pipeline gerou
  [daily-digest]="16 6 * * *"         # envia o resumo diário
  [drain-report-exports]="20 6 * * *" # processa exportações pedidas
  [retention]="24 6 * * *"            # limpa dado fora da janela de retenção
  [operational-watchdog]="32 6 * * *" # confere que o pipeline do dia rodou
)

require_operational_config() {
  validate_monitoring_notification_channels
  require_value "MPLACAS_TELEGRAM_ALERT_CHAT_ID" "${MPLACAS_TELEGRAM_ALERT_CHAT_ID:-}"
  require_value "MPLACAS_CLOUD_JOB_PLANT_NAME" "${MPLACAS_CLOUD_JOB_PLANT_NAME:-}"
  require_value \
    "MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH" \
    "${MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH:-}"

  python3 - \
    "$MPLACAS_TELEGRAM_ALERT_CHAT_ID" \
    "$MPLACAS_CLOUD_JOB_PLANT_NAME" \
    "$MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH" \
    "${MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH:-}" <<'PY'
import decimal
import sys

for value in sys.argv[1:3]:
    if "," in value or "\n" in value or "\r" in value:
        raise SystemExit("job environment values cannot contain commas or newlines")

for value in sys.argv[3:]:
    if not value:
        continue
    try:
        parsed = decimal.Decimal(value)
    except decimal.InvalidOperation as exc:
        raise SystemExit("expected production must be a decimal") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise SystemExit("expected production must be finite and positive")
PY
}

require_single_secret() {
  local secret_name="$1"
  gcloud secrets describe "$secret_name" --project "$GCP_PROJECT_ID" >/dev/null
  [[ "$(count_enabled_secret_versions "$secret_name")" == "1" ]] || die \
    "${secret_name} must have exactly one ENABLED version"
}

job_name() {
  printf '%s-%s\n' "$GCP_OPERATIONAL_JOB_PREFIX" "$1"
}

# Keeps this script's job list in sync with the guardrail allowlist that
# audit-costs.sh enforces (infra/gcp/lib.sh:MPLACAS_EXPECTED_SCHEDULER_JOBS).
# A command deployed here but missing from the allowlist would make the next
# audit-costs.sh run falsely flag it as a prohibited resource.
require_operational_commands_are_allowlisted() {
  local command_name
  local name
  for command_name in "${OPERATIONAL_COMMANDS[@]}"; do
    name="$(job_name "$command_name")"
    scheduler_job_is_expected "$name" || die \
      "operational command missing from MPLACAS_EXPECTED_SCHEDULER_JOBS: ${name}"
  done
}

deploy_job() {
  local command_name="$1"
  local name
  name="$(job_name "$command_name")"

  gcloud run jobs deploy "$name" \
    --image "$IMAGE" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --service-account "$(runtime_service_account_email)" \
    --cpu "$GCP_CPU" \
    --memory "$GCP_MEMORY" \
    --tasks 1 \
    --parallelism 1 \
    --max-retries 1 \
    --task-timeout 30m \
    --set-env-vars "$JOB_ENV_VARS" \
    --set-secrets "$JOB_SECRETS" \
    --command python \
    "--args=-m,mplacas.cloud_jobs,${command_name}" \
    --quiet

  gcloud run jobs add-iam-policy-binding "$name" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --member="serviceAccount:$(scheduler_service_account_email)" \
    --role="roles/run.invoker" \
    --quiet >/dev/null
}

upsert_schedule() {
  local command_name="$1"
  local name
  local uri
  name="$(job_name "$command_name")"
  uri="https://${GCP_REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${GCP_PROJECT_ID}/jobs/${name}:run"

  if gcloud scheduler jobs describe "$name" \
    --location "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$name" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --schedule "${OPERATIONAL_SCHEDULES[$command_name]}" \
      --time-zone "$MPLACAS_TIMEZONE" \
      --uri "$uri" \
      --http-method POST \
      --oauth-service-account-email "$(scheduler_service_account_email)" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
      --attempt-deadline 30m \
      --max-retry-attempts 1 \
      --quiet
  else
    gcloud scheduler jobs create http "$name" \
      --location "$GCP_REGION" \
      --project "$GCP_PROJECT_ID" \
      --schedule "${OPERATIONAL_SCHEDULES[$command_name]}" \
      --time-zone "$MPLACAS_TIMEZONE" \
      --uri "$uri" \
      --http-method POST \
      --oauth-service-account-email "$(scheduler_service_account_email)" \
      --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
      --attempt-deadline 30m \
      --max-retry-attempts 1 \
      --quiet
  fi
}

load_config
require_gcloud
require_authenticated_gcloud
require_python
configure_gcloud_project
validate_billing_enabled
require_operational_commands_are_allowlisted
require_operational_config
ensure_runtime_service_account
ensure_scheduler_service_account

for secret_name in \
  "$SECRET_DATABASE_URL" \
  "$SECRET_OPERATIONS_KEY" \
  "$SECRET_JWT" \
  "$SECRET_TELEGRAM_BOT_TOKEN" \
  "$SECRET_NEP_ACCOUNT" \
  "$SECRET_NEP_PASSWORD"; do
  require_single_secret "$secret_name"
done

IMAGE="$(cloud_run_service_image)"
[[ -n "$IMAGE" ]] || die "deployed service image was not found"

JOB_ENV_VARS="MPLACAS_ENVIRONMENT=production,MPLACAS_TIMEZONE=${MPLACAS_TIMEZONE},MPLACAS_GCP_PROJECT_ID=${GCP_PROJECT_ID},MPLACAS_CLOUD_TRACE_ENABLED=true,MPLACAS_CLOUD_METRICS_ENABLED=true,MPLACAS_TELEGRAM_ALERT_CHAT_ID=${MPLACAS_TELEGRAM_ALERT_CHAT_ID},MPLACAS_CLOUD_JOB_PLANT_NAME=${MPLACAS_CLOUD_JOB_PLANT_NAME},MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH=${MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH}"
if [[ -n "${MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH:-}" ]]; then
  JOB_ENV_VARS="${JOB_ENV_VARS},MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH=${MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH}"
fi
JOB_SECRETS="MPLACAS_DATABASE_URL=${SECRET_DATABASE_URL}:latest,MPLACAS_OPERATIONS_API_KEY=${SECRET_OPERATIONS_KEY}:latest,MPLACAS_JWT_SECRET=${SECRET_JWT}:latest,MPLACAS_TELEGRAM_BOT_TOKEN=${SECRET_TELEGRAM_BOT_TOKEN}:latest,MPLACAS_NEP_ACCOUNT=${SECRET_NEP_ACCOUNT}:latest,MPLACAS_NEP_PASSWORD=${SECRET_NEP_PASSWORD}:latest"

confirm_exact \
  "PROVISION-OPERATIONS-${GCP_PROJECT_ID}" \
  "Type PROVISION-OPERATIONS-${GCP_PROJECT_ID} to deploy jobs and schedules:"

for command_name in "${OPERATIONAL_COMMANDS[@]}"; do
  deploy_job "$command_name"
  upsert_schedule "$command_name"
done

upsert_monitoring_policy \
  "operational_job_failure" \
  "${SCRIPT_DIR}/monitoring/operational-job-failure.json"
upsert_monitoring_policy \
  "operational_watchdog_absence" \
  "${SCRIPT_DIR}/monitoring/operational-watchdog-absence.json"

SMOKE_JOB_NAME="$(job_name smoke)"
gcloud run jobs deploy "$SMOKE_JOB_NAME" \
  --image "$IMAGE" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --service-account "$(runtime_service_account_email)" \
  --cpu "$GCP_CPU" \
  --memory "$GCP_MEMORY" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout 5m \
  --set-env-vars "$JOB_ENV_VARS" \
  --set-secrets "$JOB_SECRETS" \
  --command python \
  --args=-m,mplacas.cloud_jobs,smoke \
  --quiet

log "operational jobs, schedules, and alert policies provisioned idempotently"
log "run infra/gcp/verify-operations.sh to validate and prime the watchdog metric"
