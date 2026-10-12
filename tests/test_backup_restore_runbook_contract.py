from __future__ import annotations

from pathlib import Path


RUNBOOK = Path("docs/backup-restore-runbook.md")
AUTOMATION = Path("infra/backup/run-restore-drill.sh")
WORKFLOW = Path(".github/workflows/restore-drill.yml")


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


def test_restore_drill_is_scheduled_and_fail_closed() -> None:
    script = AUTOMATION.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    required_script_terms = {
        "MPLACAS_RESTORE_CONFIRM_HOST",
        "restore target must use a different host/branch than production",
        "pg_dump",
        "pg_restore",
        "--exit-on-error",
        "alembic.ini upgrade head",
        "http://127.0.0.1:18080/ready",
        '"decision": "approved"',
        "--cipher-algo AES256",
    }
    assert all(term in script for term in required_script_terms)
    assert '--dbname "$SOURCE_DSN"' in script
    assert 'PGDATABASE="$MPLACAS_BACKUP_SOURCE_URL"' not in script
    assert 'PGDATABASE="$MPLACAS_RESTORE_DATABASE_URL"' not in script
    assert '"postgresql+asyncpg"' in script
    assert 'source_url._replace(scheme="postgresql")' in script
    assert '--dbname "$MPLACAS_RESTORE_DATABASE_URL"' not in script
    assert 'PGPASSWORD="${RESTORE_CONNECTION[3]}"' in script
    assert script.count('PGHOST="${RESTORE_CONNECTION[0]}"') == 2
    assert script.count('PGSSLMODE="${RESTORE_CONNECTION[5]}"') == 2
    # A agenda diária É o contrato de RPO (24 h), não um detalhe de conveniência:
    # sem ela o único recurso é o PITR do Neon Free, que cobre 6 h e não protege
    # contra perda da conta nem contra corrupção descoberta mais tarde.
    #
    # Este teste já existiu como `..._is_automated_...`, foi quebrado em silêncio
    # quando a agenda saiu (2026-08-25) e passou 2 dias deixando a `main` vermelha
    # — ver achado A-10 de docs/AUDITORIA_BIG_TECH_2026-08-26.md. Se a agenda
    # precisar sair de novo, que seja por decisão registrada que atualize este
    # teste junto, não por omissão.
    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "0 7 * * *"' in workflow
    # Fuso explícito: o cron do GitHub é UTC por padrão, e sem isto o drill
    # rodaria às 04:00 local, ANTES do ciclo operacional das 06:07 — o snapshot
    # sairia sem o processamento daquela manhã.
    assert "timezone: America/Sao_Paulo" in workflow
    assert "retention-days: 35" in workflow
    assert "environment: production-restore-drill" in workflow
    assert "postgres:18@sha256:" in workflow
    assert "postgresql-client-18" in workflow
    assert 'export PATH="/usr/lib/postgresql/18/bin:$PATH"' in workflow
    assert 'echo "/usr/lib/postgresql/18/bin" >> "$GITHUB_PATH"' in workflow
    assert "pg_dump --version" in workflow
    assert "https://apt.postgresql.org/pub/repos/apt" in workflow
    assert "signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg" in workflow
    assert "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8" in workflow
    assert "POSTGRES_HOST_AUTH_METHOD: trust" in workflow
    assert (
        "MPLACAS_RESTORE_DATABASE_URL: "
        "postgresql://postgres@localhost:5432/mplacas_restore_check"
    ) in workflow
    assert "MPLACAS_RESTORE_CONFIRM_HOST: localhost" in workflow
    assert "secrets.MPLACAS_RESTORE_DATABASE_URL" not in workflow
    assert "secrets.MPLACAS_RESTORE_CONFIRM_HOST" not in workflow
    assert 'loopback_hosts = {"localhost", "127.0.0.1", "::1"}' in script
    assert "remote restore URL must contain a password" in script
    assert 'default_sslmode = "disable" if host in loopback_hosts else "require"' in script
    assert 'sslmode not in {"require", "verify-ca", "verify-full"}' in script
    assert "remote restore URL must require TLS" in script
    assert "Open deduplicated restore incident" in workflow


def test_restore_drill_objectives_are_explicit() -> None:
    content = RUNBOOK.read_text(encoding="utf-8")

    assert "**RPO:** no máximo 24 horas" in content
    assert "**RTO:** até 4 horas" in content
    assert "**Retenção:** 35 dias" in content
    assert "MPLACAS_RESTORE_DRILL_OWNER" in content
    assert "PITR" in content
