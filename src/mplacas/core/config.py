from __future__ import annotations

import uuid
from decimal import Decimal
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

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
    external_http_allowed_hosts: str = "api.nepviewer.net,archive-api.open-meteo.com"
    climate_maximum_backfill_days: int = 366
    pipeline_stale_lock_timeout_minutes: int = 60
    outbox_stale_lock_timeout_minutes: int = 15
    outbox_dispatch_batch_size: int = 100
    outbox_max_attempts: int = 10
    explanation_api_url: HttpUrl | None = None
    explanation_api_key: SecretStr | None = None
    explanation_model: str | None = None
    explanation_timeout_seconds: float = 15.0
    operations_api_key: SecretStr | None = None
    operations_read_api_key: SecretStr | None = None
    operations_read_plant_ids: str | None = None
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

    @property
    def external_http_allowed_host_set(self) -> frozenset[str]:
        return frozenset(
            host.strip().lower()
            for host in self.external_http_allowed_hosts.split(",")
            if host.strip()
        )

    @property
    def operations_read_plant_id_set(self) -> frozenset[uuid.UUID] | None:
        if self.operations_read_plant_ids is None:
            return None
        return frozenset(
            uuid.UUID(value.strip())
            for value in self.operations_read_plant_ids.split(",")
        )

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

    @field_validator("outbox_stale_lock_timeout_minutes", "outbox_max_attempts")
    @classmethod
    def _validate_positive_outbox_value(cls, value: int) -> int:
        if value < 1:
            raise ValueError("outbox retry and lock values must be positive")
        return value

    @field_validator("outbox_dispatch_batch_size")
    @classmethod
    def _validate_outbox_batch_size(cls, value: int) -> int:
        if not 1 <= value <= 1000:
            raise ValueError("outbox dispatch batch size must be between 1 and 1000")
        return value

    @field_validator("operations_read_plant_ids")
    @classmethod
    def _validate_operations_read_plant_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw_values = [item.strip() for item in value.split(",") if item.strip()]
        if not raw_values:
            raise ValueError("read credential plant scope must contain at least one UUID")
        try:
            normalized = tuple(dict.fromkeys(str(uuid.UUID(item)) for item in raw_values))
        except ValueError as exc:
            raise ValueError("read credential plant scope contains an invalid UUID") from exc
        return ",".join(normalized)

    @model_validator(mode="after")
    def _validate_environment(self) -> Settings:
        if self.operations_read_plant_ids is not None and (
            self.operations_read_api_key is None
            or not self.operations_read_api_key.get_secret_value().strip()
        ):
            raise ValueError("read credential plant scope requires an operational read API key")
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
        allowed_hosts = self.external_http_allowed_host_set
        if not allowed_hosts:
            raise ValueError("at least one external HTTP host must be allowed in production")
        _validate_production_external_url(
            name="MPLACAS_NEP_BASE_URL",
            url=str(self.nep_base_url),
            allowed_hosts=allowed_hosts,
        )
        _validate_production_external_url(
            name="MPLACAS_CLIMATE_ARCHIVE_BASE_URL",
            url=str(self.climate_archive_base_url),
            allowed_hosts=allowed_hosts,
        )
        if self.explanation_api_url is not None:
            _validate_production_external_url(
                name="MPLACAS_EXPLANATION_API_URL",
                url=str(self.explanation_api_url),
                allowed_hosts=allowed_hosts,
            )
        return self

    def safe_summary(self) -> dict[str, object]:
        read_scope = "not_configured"
        if self.operations_read_api_key is not None:
            read_scope = (
                "restricted" if self.operations_read_plant_ids is not None else "unrestricted"
            )
        return {
            "environment": self.env,
            "database_backend": _database_backend(self.database_url),
            "port": self.port,
            "timezone": self.timezone,
            "operational_auth_configured": self.operations_api_key is not None,
            "operational_read_auth_configured": self.operations_read_api_key is not None,
            "operational_read_plant_scope": read_scope,
            "operational_read_plant_count": len(self.operations_read_plant_id_set or ()),
            "external_http_allowed_host_count": len(self.external_http_allowed_host_set),
        }


def _database_backend(database_url: str) -> str:
    lowered = database_url.strip().lower()
    if lowered.startswith("sqlite"):
        return "sqlite"
    if lowered.startswith("postgresql") or lowered.startswith("postgres"):
        return "postgresql"
    return "unknown"


def _validate_production_external_url(
    *,
    name: str,
    url: str,
    allowed_hosts: frozenset[str],
) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError(f"{name} must use HTTPS in production")
    if not host or host not in allowed_hosts:
        raise ValueError(f"{name} host is not in MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
