"""Tests for scripts/set-admin-password.py.

Tests cover URL normalization, sslmode/channel_binding stripping, and password
validation. No real database connection is required — DB calls are mocked.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import helpers from the script under test.
# The script filename uses a hyphen, which prevents normal import, so we load
# it via importlib and register it under an alias.
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "set-admin-password.py"


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("set_admin_password", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("set_admin_password", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return sys.modules["set_admin_password"]


_mod = _load_script()
_normalize_database_url = _mod._normalize_database_url  # type: ignore[attr-defined]
_mask_url = _mod._mask_url  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------

class TestNormalizeDatabaseUrl:
    def test_postgres_scheme_converted(self) -> None:
        result = _normalize_database_url("postgres://user:pass@host/db")
        assert result.startswith("postgresql+asyncpg://")

    def test_postgresql_scheme_converted(self) -> None:
        result = _normalize_database_url("postgresql://user:pass@host/db")
        assert result.startswith("postgresql+asyncpg://")

    def test_asyncpg_scheme_unchanged(self) -> None:
        url = "postgresql+asyncpg://user:pass@host/db"
        result = _normalize_database_url(url)
        assert result == url

    def test_sslmode_removed(self) -> None:
        url = "postgresql://user:pass@host/db?sslmode=require"
        result = _normalize_database_url(url)
        assert "sslmode" not in result
        assert result.startswith("postgresql+asyncpg://")

    def test_channel_binding_removed(self) -> None:
        url = "postgresql://user:pass@host/db?channel_binding=require"
        result = _normalize_database_url(url)
        assert "channel_binding" not in result

    def test_both_unsupported_params_removed(self) -> None:
        url = "postgresql://user:pass@host/db?sslmode=require&channel_binding=prefer"
        result = _normalize_database_url(url)
        assert "sslmode" not in result
        assert "channel_binding" not in result

    def test_other_params_preserved(self) -> None:
        url = "postgresql://user:pass@host/db?sslmode=require&application_name=mplacas"
        result = _normalize_database_url(url)
        assert "application_name=mplacas" in result
        assert "sslmode" not in result

    def test_no_params_unchanged(self) -> None:
        url = "postgresql+asyncpg://user:pass@host/db"
        result = _normalize_database_url(url)
        assert result == url

    def test_invalid_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            _normalize_database_url("sqlite:///./test.db")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            _normalize_database_url("")


# ---------------------------------------------------------------------------
# Password validation (tested via _read_password_interactively mock path)
# ---------------------------------------------------------------------------

class TestPasswordValidation:
    """Validate the interactive password-reading logic without real tty input."""

    def test_empty_password_rejected(self) -> None:
        """An empty password must cause sys.exit(1)."""
        with patch("getpass.getpass", return_value=""):
            with pytest.raises(SystemExit) as exc_info:
                _mod._read_password_interactively()  # type: ignore[attr-defined]
            assert exc_info.value.code == 1

    def test_short_password_rejected(self) -> None:
        """Passwords under 12 characters must cause sys.exit(1)."""
        with patch("getpass.getpass", return_value="short"):
            with pytest.raises(SystemExit) as exc_info:
                _mod._read_password_interactively()  # type: ignore[attr-defined]
            assert exc_info.value.code == 1

    def test_mismatched_confirmation_rejected(self) -> None:
        """Non-matching confirmation must cause sys.exit(1)."""
        responses = iter(["senha-longa-ok", "senha-diferente-ok"])
        with patch("getpass.getpass", side_effect=lambda _: next(responses)):
            with pytest.raises(SystemExit) as exc_info:
                _mod._read_password_interactively()  # type: ignore[attr-defined]
            assert exc_info.value.code == 1

    def test_valid_password_returned(self) -> None:
        """Matching password of sufficient length must be returned."""
        senha = "senha-valida-longa"
        responses = iter([senha, senha])
        with patch("getpass.getpass", side_effect=lambda _: next(responses)):
            result = _mod._read_password_interactively()  # type: ignore[attr-defined]
        assert result == senha


# ---------------------------------------------------------------------------
# URL masking
# ---------------------------------------------------------------------------

class TestMaskUrl:
    def test_masks_credentials(self) -> None:
        url = "postgresql+asyncpg://user:secret@host:5432/db"
        masked = _mask_url(url)
        assert "secret" not in masked

    def test_no_credentials_unchanged(self) -> None:
        url = "postgresql+asyncpg://host:5432/db"
        masked = _mask_url(url)
        # Should not raise and should not contain literal "user:pass".
        assert "host" in masked
