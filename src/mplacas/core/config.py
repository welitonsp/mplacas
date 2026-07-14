from __future__ import annotations

from functools import lru_cache
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração central carregada exclusivamente por variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_prefix="MPLACAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("MPLACAS_ENV", "MPLACAS_ENVIRONMENT"),
    )
    log_level: str = "INFO"
    timezone: str = "America/Sao_Paulo"
    database_url: str = Field(default="sqlite+aiosqlite:///./mplacas.db", repr=False)
    port: int = Field(default=8080, validation_alias="PORT")
    readiness_timeout_seconds: float = 3.0
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
    cloud_job_plant_id: str | None = None
    cloud_job_expected_daily_production_kwh: Decimal | None = None
    cloud_job_expected_cycle_production_kwh: Decimal | None = None
    cloud_job_anomaly_days: int = 7

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

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @field_validator("readiness_timeout_seconds", "request_timeout_seconds")
    @classmethod
    def _validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @field_validator("cloud_job_anomaly_days")
    @classmethod
    def _validate_anomaly_days(cls, value: int) -> int:
        if not 1 <= value <= 90:
            raise ValueError("cloud job anomaly days must be between 1 and 90")
        return value

    @model_validator(mode="after")
    def _validate_environment(self) -> Settings:
        if self.env != "production":
            return self
        database_url = self.database_url.strip().lower()
        if not database_url:
            raise ValueError("database URL is required in production")
        if database_url.startswith("sqlite") or ":memory:" in database_url:
            raise ValueError("SQLite is not allowed in production")
        if not (
            database_url.startswith("postgresql")
            or database_url.startswith("postgres")
        ):
            raise ValueError("PostgreSQL database URL is required in production")
        if (
            self.operations_api_key is None
            or not self.operations_api_key.get_secret_value().strip()
        ):
            raise ValueError("operational API key is required in production")
        return self

    def safe_summary(self) -> dict[str, object]:
        return {
            "environment": self.env,
            "database_backend": _database_backend(self.database_url),
            "port": self.port,
            "timezone": self.timezone,
            "operational_auth_configured": self.operations_api_key is not None,
        }


def _database_backend(database_url: str) -> str:
    lowered = database_url.strip().lower()
    if lowered.startswith("sqlite"):
        return "sqlite"
    if lowered.startswith("postgresql") or lowered.startswith("postgres"):
        return "postgresql"
    return "unknown"


@lru_cache
def get_settings() -> Settings:
    return Settings()
