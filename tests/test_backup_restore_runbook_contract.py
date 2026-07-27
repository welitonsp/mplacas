from __future__ import annotations

from pathlib import Path


RUNBOOK = Path("docs/backup-restore-runbook.md")


def test_backup_restore_runbook_exists() -> None:
    assert RUNBOOK.exists()


def test_backup_restore_runbook_has_backup_and_restore_contract() -> None:
    content = RUNBOOK.read_text(encoding="utf-8")

    required_terms = [
        "MPLACAS_DATABASE_URL",
        "MPLACAS_RESTORE_DATABASE_URL",
        "pg_dump",
        "pg_restore",
        "sha256sum",
        "alembic_version",
        "curl -fsS http://127.0.0.1:8080/ready",
        "banco descartável",
        "fora do repositório",
    ]

    missing = [term for term in required_terms if term not in content]
    assert not missing, f"Runbook missing required terms: {missing}"


def test_backup_restore_runbook_requires_restore_rehearsal() -> None:
    content = RUNBOOK.read_text(encoding="utf-8").lower()

    assert "restauração de ensaio" in content
    assert "falha de `/ready` bloqueia promoção do backup" in content
    assert "não usa o banco de produção como destino" in content
