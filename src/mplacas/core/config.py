from __future__ import annotations

import sys
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
    gcp_project_id: str | None = None
    cloud_trace_enabled: bool = False
    trace_sample_rate: float = 0.1
    cloud_metrics_enabled: bool = False
    metrics_export_interval_seconds: int = 60
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
    credential_pepper: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_allowed_user_id: int | None = None
    telegram_alert_chat_id: str | None = None
    telegram_document_max_bytes: int = 10_000_000
    telegram_pdf_max_pages: int = 10
    telegram_pdf_parse_timeout_seconds: float = 5.0
    telegram_pdf_parse_cpu_seconds: int = 3
    telegram_pdf_parse_memory_bytes: int = 268_435_456
    bill_text_max_bytes: int = 250_000
    request_timeout_seconds: float = 20.0
    cloud_job_plant_name: str | None = None
    cloud_job_expected_daily_production_kwh: Decimal | None = None
    cloud_job_expected_cycle_production_kwh: Decimal | None = None
    cloud_job_anomaly_days: int = 7
    retention_job_runs_days: int = 90
    retention_pipeline_executions_days: int = 90
    retention_outbox_events_days: int = 30
    retention_collection_tasks_days: int = 30
    retention_alert_delivery_records_days: int = 365
    retention_auth_sessions_days: int = 90
    retention_login_rate_limits_days: int = 30
    retention_user_invitations_days: int = 365
    retention_daily_energy_days: int = 1825
    retention_climate_observations_days: int = 1825
    report_export_bucket: str | None = None
    report_export_url_ttl_seconds: int = 900
    jwt_secret: SecretStr | None = None
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_audience: str = "mplacas-api"
    jwt_key_id: str = "v1"
    jwt_previous_secret: SecretStr | None = None
    jwt_previous_key_id: str | None = None
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 1_209_600
    auth_login_max_attempts: int = 5
    auth_login_window_seconds: int = 900
    auth_login_lockout_seconds: int = 900
    auth_invitation_ttl_seconds: int = 259_200
    cors_allowed_origins: str | None = None
    dashboard_url: HttpUrl = HttpUrl("https://mplacas-frontend.pages.dev/dashboard")

    @property
    def jwt_configured(self) -> bool:
        return self.jwt_secret is not None

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        if not self.cors_allowed_origins:
            return []
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def nep_configured(self) -> bool:
        return bool(self.nep_account and self.nep_password)

    @property
    def telegram_configured(self) -> bool:
        """Whether the global Telegram webhook infrastructure is set up.

        ``telegram_allowed_user_id`` is intentionally excluded: since it moved
        to a per-organization column (``organizations.telegram_allowed_user_id``),
        it is no longer a global setting and has no bearing on whether the
        shared bot token / webhook secret infrastructure is ready. Including
        it here would make this health signal misleading — reporting
        ``False`` even though every organization is correctly configured via
        its own column, or ``True`` based on a legacy env var that no
        organization actually uses.
        """
        return bool(self.telegram_bot_token and self.telegram_webhook_secret)

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

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @field_validator(
        "readiness_timeout_seconds",
        "request_timeout_seconds",
        "telegram_pdf_parse_timeout_seconds",
    )
    @classmethod
    def _validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @field_validator(
        "telegram_document_max_bytes",
        "telegram_pdf_max_pages",
        "telegram_pdf_parse_cpu_seconds",
        "telegram_pdf_parse_memory_bytes",
        "bill_text_max_bytes",
    )
    @classmethod
    def _validate_positive_document_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("document processing limits must be positive")
        return value

    @field_validator(
        "jwt_access_ttl_seconds",
        "jwt_refresh_ttl_seconds",
        "auth_login_max_attempts",
        "auth_login_window_seconds",
        "auth_login_lockout_seconds",
        "auth_invitation_ttl_seconds",
    )
    @classmethod
    def _validate_positive_auth_value(cls, value: int) -> int:
        if value < 1:
            raise ValueError("authentication timing and limit values must be positive")
        return value

    @field_validator("jwt_audience", "jwt_key_id", "jwt_previous_key_id")
    @classmethod
    def _validate_jwt_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")
        if not cleaned or len(cleaned) > 128 or any(char not in allowed for char in cleaned):
            raise ValueError("JWT audience and key identifiers must be safe non-empty values")
        return cleaned

    @field_validator("trace_sample_rate")
    @classmethod
    def _validate_trace_sample_rate(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("trace sample rate must be between 0 and 1")
        return value

    @field_validator("metrics_export_interval_seconds")
    @classmethod
    def _validate_metrics_export_interval(cls, value: int) -> int:
        if not 10 <= value <= 3600:
            raise ValueError("metrics export interval must be between 10 and 3600 seconds")
        return value

    @field_validator("gcp_project_id")
    @classmethod
    def _normalize_gcp_project_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

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

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # asyncpg requires the postgresql+asyncpg:// scheme.
        # Neon and many PaaS providers emit postgres:// or postgresql:// — normalize both.
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value[len("postgres://"):]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://"):]
        # asyncpg does not accept sslmode/channel_binding as URL params — SSL is
        # handled via connect_args in session.py. Strip these psycopg2-style params.
        pg_asyncpg = "postgresql+asyncpg://" in value
        has_unsupported_params = "sslmode=" in value or "channel_binding=" in value
        if pg_asyncpg and has_unsupported_params:
            from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
            parts = urlsplit(value)
            params = {
                k: v for k, v in parse_qs(parts.query, keep_blank_values=True).items()
                if k not in ("sslmode", "channel_binding")
            }
            query = urlencode({k: v[0] for k, v in params.items()})
            value = urlunsplit(parts._replace(query=query))
        return value

    @model_validator(mode="after")
    def _validate_environment(self) -> Settings:
        configured_jwt_secrets = [
            secret
            for secret in (self.jwt_secret, self.jwt_previous_secret)
            if secret is not None
        ]
        if any(
            len(secret.get_secret_value().encode("utf-8")) < 32
            for secret in configured_jwt_secrets
        ):
            raise ValueError("JWT secrets must contain at least 32 bytes")
        if (self.jwt_previous_secret is None) != (self.jwt_previous_key_id is None):
            raise ValueError("previous JWT secret and key id must be configured together")
        if self.jwt_previous_key_id == self.jwt_key_id:
            raise ValueError("current and previous JWT key ids must differ")
        if self.cloud_trace_enabled and self.gcp_project_id is None:
            raise ValueError("Cloud Trace requires MPLACAS_GCP_PROJECT_ID")
        if self.cloud_metrics_enabled and self.gcp_project_id is None:
            raise ValueError("Cloud Monitoring requires MPLACAS_GCP_PROJECT_ID")
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
        return {
            "environment": self.env,
            "database_backend": _database_backend(self.database_url),
            "port": self.port,
            "timezone": self.timezone,
            "structured_logging": self.env == "production",
            "cloud_trace_enabled": self.cloud_trace_enabled,
            "trace_sample_rate": self.trace_sample_rate,
            "cloud_metrics_enabled": self.cloud_metrics_enabled,
            "metrics_export_interval_seconds": self.metrics_export_interval_seconds,
            "operational_auth_configured": self.operations_api_key is not None,
            "jwt_auth_configured": self.jwt_configured,
            "auth_login_max_attempts": self.auth_login_max_attempts,
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
    # Skip .env file when running under pytest so monkeypatch.delenv works correctly.
    # In production and development, .env is loaded normally.
    env_file: str | None = None if "pytest" in sys.modules else ".env"
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
