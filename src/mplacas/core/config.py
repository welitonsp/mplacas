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
    nep_base_url: HttpUrl = HttpUrl("https://api.nepviewer.net/v2")
    nep_account: str | None = None
    nep_password: SecretStr | None = None
    request_timeout_seconds: float = 20.0

    @property
    def nep_configured(self) -> bool:
        return bool(self.nep_account and self.nep_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
