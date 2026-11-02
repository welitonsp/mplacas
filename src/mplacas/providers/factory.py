"""Monta o provedor certo para a marca de uma conexão (ADR-091/092)."""

from __future__ import annotations

import httpx

from mplacas.core.config import get_settings
from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN, NEPVIEWER
from mplacas.providers.growatt.client import GrowattClient
from mplacas.providers.growatt.openapi import GrowattOpenApiClient
from mplacas.providers.nepviewer.client import NepViewerClient
from mplacas.providers.resilient import ResilientSolarProvider, RetryPolicy


# Origem gravada em ``daily_energy.source`` para cada marca.
ENERGY_SOURCES = {
    NEPVIEWER: "NEPVIEWER_V2",
    GROWATT: "GROWATT_CLASSIC",
    GROWATT_TOKEN: "GROWATT_OPENAPI_V1",
}


# Clientes crus: implementam ``SolarProvider`` e precisam de ``aclose()``.
ClosableProvider = NepViewerClient | GrowattClient | GrowattOpenApiClient


def build_client(
    provider: str,
    *,
    account: str,
    password: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ClosableProvider:
    """Cliente cru da marca (uma tentativa por chamada), sem a camada de retry."""
    settings = get_settings()
    if provider == NEPVIEWER:
        return NepViewerClient(
            account=account,
            password=password,
            base_url=str(settings.nep_base_url),
            timeout_seconds=settings.request_timeout_seconds,
            transport=transport,
        )
    if provider == GROWATT:
        return GrowattClient(
            account=account,
            password=password,
            base_url=str(settings.growatt_base_url),
            timeout_seconds=settings.request_timeout_seconds,
            transport=transport,
        )
    if provider == GROWATT_TOKEN:
        # O token da OpenAPI é guardado no lugar da senha (ADR-094).
        return GrowattOpenApiClient(
            token=password,
            base_url=str(settings.growatt_openapi_url),
            timeout_seconds=settings.request_timeout_seconds,
            transport=transport,
        )
    raise ValueError("unsupported provider")


def build_resilient_provider(
    provider: str,
    *,
    account: str,
    password: str,
    retry_policy: RetryPolicy | None = None,
) -> tuple[ClosableProvider, ResilientSolarProvider]:
    """``(cliente, provedor_resiliente)``: injete o segundo; feche o primeiro."""
    client = build_client(provider, account=account, password=password)
    return client, ResilientSolarProvider(client, policy=retry_policy)
