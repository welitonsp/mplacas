"""Unit tests for the administrative password utility."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "set-admin-password.py"


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("set_admin_password", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["set_admin_password"] = module
    spec.loader.exec_module(module)
    return module


_mod = _load_script()


class TestPasswordValidation:
    def test_empty_password_rejected(self) -> None:
        with patch("getpass.getpass", return_value=""):
            with pytest.raises(SystemExit) as exc_info:
                _mod._read_password_interactively()
        assert exc_info.value.code == 1

    def test_short_password_rejected(self) -> None:
        with patch("getpass.getpass", return_value="short"):
            with pytest.raises(SystemExit) as exc_info:
                _mod._read_password_interactively()
        assert exc_info.value.code == 1

    def test_mismatched_confirmation_rejected(self) -> None:
        answers = iter(["senha-valida-longa", "senha-diferente-longa"])
        with patch("getpass.getpass", side_effect=lambda _: next(answers)):
            with pytest.raises(SystemExit) as exc_info:
                _mod._read_password_interactively()
        assert exc_info.value.code == 1

    def test_valid_password_returned(self) -> None:
        password = "senha-valida-longa"
        answers = iter([password, password])
        with patch("getpass.getpass", side_effect=lambda _: next(answers)):
            assert _mod._read_password_interactively() == password


class TestMasking:
    def test_mask_url_hides_credentials_and_host(self) -> None:
        masked = _mod._mask_url(
            "postgresql+asyncpg://admin:supersecret@private.neon.tech:5432/neondb"
        )
        assert "admin" not in masked
        assert "supersecret" not in masked
        assert "private.neon.tech" not in masked

    def test_sanitizes_exception_with_full_dsn(self) -> None:
        raw_url = (
            "postgresql://admin:supersecret@ep-private.us-east-1.aws.neon.tech/neondb"
            "?sslmode=require"
        )
        exc = RuntimeError(f"connection failed for {raw_url}")
        message = _mod._sanitize_exception_message(exc, raw_url)
        assert "admin" not in message
        assert "supersecret" not in message
        assert "ep-private" not in message
        assert "postgresql://" not in message
        assert "<database-url>" in message

    def test_sanitizer_returns_bounded_message(self) -> None:
        message = _mod._sanitize_exception_message(RuntimeError("x" * 1000))
        assert len(message) == 500
