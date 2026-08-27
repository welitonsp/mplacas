from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_operational_workflow_runs_from_src_with_runtime_lock() -> None:
    workflow = (ROOT / ".github/workflows/operational-jobs.yml").read_text(encoding="utf-8")

    assert "PYTHONPATH: ${{ github.workspace }}/src" in workflow
    assert "pip install --require-hashes -r requirements.lock" in workflow
    assert "pip install --no-deps --no-build-isolation -e ." not in workflow
    assert "smoke --operational" in workflow


def test_migration_workflow_runs_from_src_with_runtime_lock() -> None:
    workflow = (ROOT / ".github/workflows/migrate.yml").read_text(encoding="utf-8")

    assert "PYTHONPATH: ${{ github.workspace }}/src" in workflow
    assert "pip install --require-hashes -r requirements.lock" in workflow
    assert "pip install --no-deps --no-build-isolation -e ." not in workflow


def test_render_waits_for_ci_and_keeps_runtime_secrets_out_of_git() -> None:
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "autoDeployTrigger: checksPass" in blueprint
    for name in (
        "MPLACAS_DATABASE_URL",
        "MPLACAS_OPERATIONS_API_KEY",
        "MPLACAS_JWT_SECRET",
        "MPLACAS_TELEGRAM_BOT_TOKEN",
        "MPLACAS_TELEGRAM_WEBHOOK_SECRET",
        "MPLACAS_TELEGRAM_ALERT_CHAT_ID",
        "MPLACAS_NEP_ACCOUNT",
        "MPLACAS_NEP_PASSWORD",
    ):
        pattern = rf"- key: {name}[^\n]*\n\s+sync: false"
        assert re.search(pattern, blueprint)


def _operational_steps() -> list[dict]:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/operational-jobs.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["daily-cycle"]["steps"]


def test_secrets_never_reach_the_dependency_install_step() -> None:
    """Segredo no `env` do job vaza para o `pip install`, que roda codigo de terceiros."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/operational-jobs.yml").read_text(encoding="utf-8")
    )
    job_env = workflow["jobs"]["daily-cycle"].get("env", {})

    assert [key for key, value in job_env.items() if "secrets." in str(value)] == []

    for step in _operational_steps():
        if "pip install" in str(step.get("run", "")):
            assert "secrets." not in str(step.get("env", {}))


def test_data_collection_is_not_blocked_by_alert_only_configuration() -> None:
    """Variavel so do digest ausente nao pode custar a telemetria irrecuperavel do dia."""
    gates = {
        step["run"].split("cloud_jobs")[1].strip().split()[0]: str(step.get("if", ""))
        for step in _operational_steps()
        if "cloud_jobs" in str(step.get("run", ""))
    }

    for command in ("collect", "drain-collection", "daily-pipeline", "retention"):
        assert "steps.smoke.outcome" in gates[command]
        assert "smoke_operational" not in gates[command]

    for command in ("dispatch-outbox", "daily-digest"):
        assert "steps.smoke_operational.outcome" in gates[command]


def test_schedule_pins_the_operation_timezone_explicitly() -> None:
    """Cron do GitHub e UTC por padrao; sem timezone o ciclo roda 3h antes do previsto."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/operational-jobs.yml").read_text(encoding="utf-8")
    )
    schedule = workflow[True]["schedule"][0]

    assert schedule["timezone"] == "America/Sao_Paulo"


def test_watchdog_observes_both_failure_modes_without_burning_the_free_tier() -> None:
    """Vigia externo (auditoria 2026-08-26, A-04/A-05).

    Cobre os dois modos de falha, que são diferentes: a API cai por ERRO, e o
    ciclo operacional falha por AUSÊNCIA — um ciclo que nunca roda não gera
    notificação nenhuma.

    A frequência é parte do contrato, não detalhe: cada verificação acorda o
    serviço no Render, cujo plano free dá 750 h/mês contra ~730 h que o mês tem.
    Um intervalo curto manteria o serviço acordado o mês inteiro e estouraria a
    franquia — o mesmo tipo de erro que estourou a cota do Neon em 2026-08-21.
    """
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    )
    texto = (ROOT / ".github/workflows/watchdog.yml").read_text(encoding="utf-8")

    assert workflow[True]["schedule"][0]["cron"] == "23 */6 * * *"
    assert "/health" in texto
    assert "operational-jobs.yml" in texto
    # Sem a porta de entrada, o vigia alertaria a cada 6 h enquanto VITE_API_URL
    # ainda apontar para o Google Cloud, antes do deploy no Render.
    assert "vigia inativo" in texto
    assert "grep -q" in texto
    # Somente leitura: um vigia não precisa de permissão de escrita.
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}


def test_backfill_e_manual_compartilha_lock_e_nao_entrega_alerta() -> None:
    """Recuperação de dias não coletados (backfill).

    Três invariantes, cada uma correspondendo a um jeito conhecido de causar
    dano com este workflow:

    1. Só manual. Backfill agendado seria consumo recorrente contra o provedor
       e contra o banco, contrariando docs/POLITICA_CUSTO_ZERO.md.
    2. Mesmo grupo de concorrência do ciclo diário. Os dois escrevendo ao mesmo
       tempo disputariam os locks por usina/data.
    3. Não executa `dispatch-outbox` nem `daily-digest`. O pipeline enfileira um
       alerta por dia processado; entregar em massa durante o backfill inunda o
       Telegram com eventos históricos.
    """
    caminho = ROOT / ".github/workflows/backfill.yml"
    workflow = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    texto = caminho.read_text(encoding="utf-8")

    gatilhos = workflow[True]
    assert "workflow_dispatch" in gatilhos
    assert "schedule" not in gatilhos

    assert workflow["concurrency"]["group"] == "operational-jobs"

    # Verificar os COMANDOS, não o texto: o cabeçalho do arquivo cita os dois
    # justamente para explicar por que não os executa.
    comandos = " ".join(
        etapa.get("run", "") for etapa in workflow["jobs"]["recuperar"]["steps"]
    )
    assert "cloud_jobs dispatch-outbox" not in comandos
    assert "cloud_jobs daily-digest" not in comandos
    assert "cloud_jobs collect" in comandos
    assert "cloud_jobs daily-pipeline" in comandos

    # Teto de dias: um ano digitado errado viraria centenas de execuções.
    assert "MAXIMO_DIAS" in texto
