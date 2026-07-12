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
    operations_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_allowed_user_id: int | None = None
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
