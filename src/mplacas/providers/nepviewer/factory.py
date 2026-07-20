from __future__ import annotations

import httpx

from mplacas.providers.nepviewer.client import NepViewerClient
from mplacas.providers.resilient import ResilientSolarProvider, RetryPolicy


def build_resilient_nepviewer(
    *,
    account: str,
    password: str,
    base_url: str = "https://api.nepviewer.net/v2",
    timeout_seconds: float = 20.0,
    retry_policy: RetryPolicy | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[NepViewerClient, ResilientSolarProvider]:
    """Compõe o cliente NEPViewer envolvido pela camada de resiliência.

    Retorna a dupla ``(cliente, provedor_resiliente)``: o provedor resiliente é
    o que deve ser injetado no domínio; o cliente é retornado apenas para que o
    chamador possa fechá-lo (``await cliente.aclose()``) ao final. Centralizar a
    composição aqui garante que a coleta nunca seja ligada à API sem a proteção
    de retry e detecção de dados incompletos.
    """
    client = NepViewerClient(
        account=account,
        password=password,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    provider = ResilientSolarProvider(client, policy=retry_policy)
    return client, provider
