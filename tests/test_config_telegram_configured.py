from __future__ import annotations

from pydantic import SecretStr

from mplacas.core.config import Settings


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_telegram_configured_true_without_global_allowed_user_id() -> None:
    """telegram_allowed_user_id is now per-organization; the global
    infrastructure signal must not depend on it being set."""
    settings = _settings(
        telegram_bot_token=SecretStr("token"),
        telegram_webhook_secret=SecretStr("secret"),
        telegram_allowed_user_id=None,
    )

    assert settings.telegram_configured is True


def test_telegram_configured_true_even_if_legacy_allowed_user_id_set() -> None:
    """A leftover legacy env var must not make the signal misleadingly true
    on its own, nor should its presence change the outcome when the real
    infra settings are also present."""
    settings = _settings(
        telegram_bot_token=SecretStr("token"),
        telegram_webhook_secret=SecretStr("secret"),
        telegram_allowed_user_id=12345,
    )

    assert settings.telegram_configured is True


def test_telegram_configured_false_without_bot_token() -> None:
    settings = _settings(
        telegram_bot_token=None,
        telegram_webhook_secret=SecretStr("secret"),
        telegram_allowed_user_id=12345,
    )

    assert settings.telegram_configured is False


def test_telegram_configured_false_without_webhook_secret() -> None:
    settings = _settings(
        telegram_bot_token=SecretStr("token"),
        telegram_webhook_secret=None,
        telegram_allowed_user_id=12345,
    )

    assert settings.telegram_configured is False
