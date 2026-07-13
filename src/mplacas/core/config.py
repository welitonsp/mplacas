from functools import lru_cache
from typing import Literal

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração central carregada exclusivamente por variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_prefix="MPLACAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    timezone: str = "America/Sao_Paulo"
    database_url: str = "sqlite+aiosqlite:///./mplacas.db"
    nep_base_url: HttpUrl = HttpUrl("https://api.nepviewer.net/v2")
    nep_account: str | None = None
    nep_password: SecretStr | None = None
    climate_archive_base_url: HttpUrl = HttpUrl("https://archive-api.open-meteo.com/v1/archive")
    climate_maximum_backfill_days: int = 366
    pipeline_stale_lock_timeout_minutes: int = 60
    explanation_api_url: HttpUrl | None = None
    explanation_api_key: SecretStr | None = None
    explanation_model: str | None = None
    explanation_timeout_seconds: float = 15.0
    operations_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_allowed_user_id: int | None = None
    telegram_alert_chat_id: str | None = None
    telegram_document_max_bytes: int = 10_000_000
    bill_text_max_bytes: int = 250_000
    request_timeout_seconds: float = 20.0

    @property
    def nep_configured(self) -> bool:
        return bool(self.nep_account and self.nep_password)

    @property
    def telegram_configured(self) -> bool:
        return bool(
            self.telegram_bot_token
            and self.telegram_webhook_secret
            and self.telegram_allowed_user_id
        )

    @property
    def telegram_alerts_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_alert_chat_id)

    @property
    def explanation_provider_configured(self) -> bool:
        return self.explanation_api_url is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
