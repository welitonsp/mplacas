from __future__ import annotations

from pathlib import Path


def test_dockerfile_uses_cloud_run_entrypoint_and_non_root_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim-bookworm" in dockerfile
    assert "USER mplacas" in dockerfile
    assert 'CMD ["python", "-m", "mplacas.cloud_run"]' in dockerfile
    assert "alembic upgrade" not in dockerfile
    assert "pytest" not in dockerfile
    assert "ruff" not in dockerfile
    assert "mypy" not in dockerfile


def test_dockerignore_excludes_local_state_and_sensitive_artifacts() -> None:
    patterns = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())

    required = {
        ".git/",
        ".github/",
        ".venv/",
        ".env",
        ".env.*",
        "tests/",
        "docs/",
        "storage/",
        "backups/",
        "*.db",
        "*.sqlite3",
        "*.dump",
        "*.pdf",
        "*.log",
    }
    assert required.issubset(patterns)
