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
