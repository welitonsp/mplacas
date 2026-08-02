from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
    )


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
        "postgresql://user:pass@ep-test-pooler.us-east-1.aws.neon.tech/neondb",
        "runtime",
    )
    assert result.returncode == 0, result.stderr


def test_runtime_rejects_direct_neon_endpoint(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test.us-east-1.aws.neon.tech/neondb",
        "runtime",
    )
    assert result.returncode != 0


def test_migration_accepts_direct_neon_endpoint(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test.us-east-1.aws.neon.tech/neondb",
        "migration",
    )
    assert result.returncode == 0, result.stderr


def test_migration_rejects_pooler(tmp_path: Path) -> None:
    result = _validate_endpoint(
        tmp_path,
        "postgresql://user:pass@ep-test-pooler.us-east-1.aws.neon.tech/neondb",
        "migration",
    )
    assert result.returncode != 0
