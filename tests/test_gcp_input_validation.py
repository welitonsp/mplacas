from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_BASH = shutil.which("bash") or (
    r"C:\Program Files\Git\bin\bash.exe"
    if sys.platform == "win32"
    else None
)

if not _BASH or not Path(_BASH).exists():
    pytest.skip("bash not available", allow_module_level=True)


def _bash(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_BASH, "-c", script, "test", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _bash_env(
    script: str, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    merged_env = {**os.environ, **env}
    return subprocess.run(
        [_BASH, "-c", script, "test", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=merged_env,
    )


_FULL_CONFIG_ENV = {
    "GCP_PROJECT_ID": "mplacas-prod",
    "GCP_REGION": "us-central1",
    "GCP_SERVICE_NAME": "mplacas-api",
    "GCP_MIGRATION_JOB_NAME": "mplacas-migrate",
    "GCP_RUNTIME_SERVICE_ACCOUNT": "mplacas-runtime",
    "GCP_SCHEDULER_SERVICE_ACCOUNT": "mplacas-scheduler",
    "GCP_OPERATIONAL_JOB_PREFIX": "mplacas",
    "GCP_MIN_INSTANCES": "0",
    "GCP_MAX_INSTANCES": "1",
    "GCP_CPU": "1",
    "GCP_MEMORY": "512Mi",
    "GCP_CONCURRENCY": "20",
    "GCP_REQUEST_TIMEOUT": "60",
    "MPLACAS_TIMEZONE": "America/Sao_Paulo",
    "MPLACAS_DASHBOARD_URL": "https://mplacas-frontend.pages.dev/dashboard",
    "MPLACAS_CONFIG_FROM_ENV": "1",
    "MPLACAS_GCP_CONFIG_FILE": "/nonexistent/config.env",
}


@pytest.mark.parametrize(
    "origins",
    [
        "https://mplacas-frontend.pages.dev",
        "https://app.example.com,https://admin.example.com:8443",
    ],
)
def test_valid_cors_origins(origins: str) -> None:
    result = _bash(
        'source infra/gcp/lib.sh; validate_cors_origins "$1"',
        origins,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "*",
        "http://app.example.com",
        "https://",
        "https://user:pass@app.example.com",
        "https://app.example.com/path",
        "https://app.example.com?x=1",
        "https://app.example.com#fragment",
        "https://app.example.com/",
        " https://app.example.com",
        "https://*.example.com",
        "https://app.example.com,,https://admin.example.com",
    ],
)
def test_invalid_cors_origins(origin: str) -> None:
    result = _bash(
        'source infra/gcp/lib.sh; validate_cors_origins "$1"',
        origin,
    )
    assert result.returncode != 0


def _validate_endpoint(tmp_path: Path, url: str, expected: str) -> subprocess.CompletedProcess[str]:
    secret_file = tmp_path / "secret"
    secret_file.write_text(url, encoding="utf-8")
    return _bash(
        'source infra/gcp/lib.sh; validate_database_endpoint_file "$1" "$2"',
        str(secret_file),
        expected,
    )


def test_runtime_accepts_neon_pooler(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test-pooler.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require",
        "runtime",
    )
    assert result.returncode == 0, result.stderr


def test_runtime_rejects_direct_neon_endpoint(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require",
        "runtime",
    )
    assert result.returncode != 0


def test_migration_accepts_direct_neon_endpoint(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require",
        "migration",
    )
    assert result.returncode == 0, result.stderr


def test_migration_rejects_pooler(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test-pooler.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require",
        "migration",
    )
    assert result.returncode != 0


def test_expected_scheduler_job_is_allowlisted() -> None:
    result = _bash(
        'source infra/gcp/lib.sh; scheduler_job_is_expected "$1"',
        "mplacas-collect",
    )
    assert result.returncode == 0, result.stderr


def test_unexpected_scheduler_job_fails_allowlist() -> None:
    result = _bash(
        'source infra/gcp/lib.sh; scheduler_job_is_expected "$1"',
        "mplacas-rogue",
    )
    assert result.returncode != 0


def test_load_config_from_env_succeeds_without_config_file_on_disk() -> None:
    result = _bash_env(
        'source infra/gcp/lib.sh; load_config; printf "%s" "$GCP_PROJECT_ID"',
        _FULL_CONFIG_ENV,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "mplacas-prod"


def test_load_config_from_env_fails_closed_with_incomplete_env() -> None:
    incomplete_env = dict(_FULL_CONFIG_ENV)
    del incomplete_env["GCP_PROJECT_ID"]
    result = _bash_env(
        'source infra/gcp/lib.sh; load_config',
        incomplete_env,
    )
    assert result.returncode != 0
    assert "GCP_PROJECT_ID is required" in result.stderr


def test_load_config_without_env_flag_still_requires_config_file() -> None:
    env = dict(_FULL_CONFIG_ENV)
    del env["MPLACAS_CONFIG_FROM_ENV"]
    result = _bash_env(
        'source infra/gcp/lib.sh; load_config',
        env,
    )
    assert result.returncode != 0
    assert "config file not found" in result.stderr
