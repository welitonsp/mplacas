from __future__ import annotations

import re
from pathlib import Path


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
