"""IP do cliente usado pelos limites de tentativa (ADR-102, § 6).

Ordem de confiança em ``resolve_client_ip``:

1. ``X-Mplacas-Client-IP`` — só quando o pedido também traz
   ``X-Mplacas-Proxy-Secret`` igual a ``MPLACAS_PROXY_SHARED_SECRET``
   (comparação em tempo constante). É o caminho do proxy do Cloudflare Pages,
   que copia o ``CF-Connecting-IP`` do navegador. Sem segredo configurado, o
   cabeçalho é ignorado por completo.
2. ``MPLACAS_TRUSTED_PROXY_HOPS = N`` definido → ``X-Forwarded-For[-N]``: cada
   proxy confiável acrescenta um endereço à direita, então o N-ésimo a partir
   da direita é quem falou com o primeiro proxy confiável. O que o cliente
   forjou fica mais à esquerda e é descartado. Nesse modo o uvicorn NÃO
   reescreve o endereço do cliente (``RestoreTcpPeerMiddleware``).
3. ``request.client.host`` — no modo transitório (``FORWARDED_ALLOW_IPS=*``),
   o que o ``ProxyHeadersMiddleware`` do uvicorn derivou do XFF.

O valor do segredo nunca é logado — nem quando confere, nem quando não confere.
O diagnóstico do login registra só booleanos e contagem, nunca endereços.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
from typing import Any

from fastapi import Request

from mplacas.core.config import Settings

logger = logging.getLogger(__name__)

CLIENT_IP_HEADER = "X-Mplacas-Client-IP"
PROXY_SECRET_HEADER = "X-Mplacas-Proxy-Secret"
# Chave no escopo ASGI com o par TCP original, antes de qualquer reescrita.
TCP_PEER_SCOPE_KEY = "mplacas.tcp_peer"

_ASGIApp = Any


class TcpPeerMiddleware:
    """Guarda no escopo o par TCP real, antes do ``ProxyHeadersMiddleware``."""

    def __init__(self, app: _ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") in ("http", "websocket"):
            scope[TCP_PEER_SCOPE_KEY] = scope.get("client")
        await self.app(scope, receive, send)


class RestoreTcpPeerMiddleware:
    """Modo ``TRUSTED_PROXY_HOPS``: desfaz a troca do cliente feita pelo XFF.

    O ``ProxyHeadersMiddleware`` continua por fora só para o
    ``X-Forwarded-Proto`` (esquema https correto); o endereço do cliente volta
    a ser o par TCP, e o IP para limites sai de ``resolve_client_ip``.
    """

    def __init__(self, app: _ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if TCP_PEER_SCOPE_KEY in scope:
            scope["client"] = scope[TCP_PEER_SCOPE_KEY]
        await self.app(scope, receive, send)


def _secret_matches(presented: str, expected: str) -> bool:
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def _valid_ip(raw: str | None) -> str | None:
    if raw is None:
        return None
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


def forwarded_for_entries(request: Request) -> list[str]:
    joined = ",".join(request.headers.getlist("x-forwarded-for"))
    return [entry.strip() for entry in joined.split(",") if entry.strip()]


def tcp_peer_host(request: Request) -> str | None:
    peer = request.scope.get(TCP_PEER_SCOPE_KEY)
    if peer:
        return str(peer[0])
    return request.client.host if request.client else None


def _from_proxy_secret(request: Request, settings: Settings) -> str | None:
    secret = settings.proxy_shared_secret
    if secret is None:
        return None
    presented = request.headers.get(PROXY_SECRET_HEADER)
    if presented is None:
        return None
    if not _secret_matches(presented, secret.get_secret_value()):
        # Só o fato é registrado; nem o valor apresentado nem o esperado.
        logger.warning("proxy_shared_secret_mismatch", extra={"path": request.url.path})
        return None
    return _valid_ip(request.headers.get(CLIENT_IP_HEADER))


def _from_trusted_hops(request: Request, hops: int) -> str | None:
    entries = forwarded_for_entries(request)
    if len(entries) < hops:
        # Menos saltos que o configurado: a cadeia não é a esperada; o par
        # TCP (o próprio proxy) é o único valor não forjável que sobra.
        return None
    return _valid_ip(entries[-hops])


def resolve_client_ip(request: Request, settings: Settings) -> str | None:
    via_proxy = _from_proxy_secret(request, settings)
    if via_proxy is not None:
        return via_proxy
    if settings.trusted_proxy_hops is not None:
        return _from_trusted_hops(request, settings.trusted_proxy_hops) or tcp_peer_host(
            request
        )
    return request.client.host if request.client else None


def log_client_ip_diagnostic(request: Request, settings: Settings, resolved: str | None) -> None:
    """Diagnóstico temporário (ADR-102 § 6): quantos proxies há na frente.

    Registra SÓ: se o par TCP é endereço privado, quantos itens tem o XFF, e
    se o IP resolvido é o próprio par TCP. Nunca endereço, usuário ou cabeçalho.
    """
    if not settings.client_ip_diagnostic:
        return
    peer = tcp_peer_host(request)
    try:
        peer_is_private = peer is not None and ipaddress.ip_address(peer).is_private
    except ValueError:
        peer_is_private = False
    logger.info(
        "client_ip_diagnostic",
        extra={
            "peer_is_private": peer_is_private,
            "forwarded_for_hops": len(forwarded_for_entries(request)),
            "resolved_matches_peer": resolved is not None and resolved == peer,
            "trusted_proxy_hops_configured": settings.trusted_proxy_hops is not None,
        },
    )
