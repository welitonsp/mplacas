"""IP do cliente usado pelos limites de tentativa (ADR-102, item 7).

Ordem de confiança:

1. ``X-Mplacas-Client-IP`` — só quando o pedido também traz
   ``X-Mplacas-Proxy-Secret`` igual a ``MPLACAS_PROXY_SHARED_SECRET``
   (comparação em tempo constante). É o caminho do proxy do Cloudflare Pages,
   que copia o ``CF-Connecting-IP`` do navegador. Sem segredo configurado, o
   cabeçalho é ignorado por completo.
2. ``request.client.host`` — já resolvido pelo uvicorn, que só aceita
   ``X-Forwarded-For`` vindo das redes de ``MPLACAS_FORWARDED_ALLOW_IPS`` (o
   proxy do Render) e, mesmo assim, pega o endereço mais à direita que não é
   dessas redes; um ``X-Forwarded-For`` forjado pelo cliente fica à esquerda e
   é descartado.

O valor do segredo nunca é logado — nem quando confere, nem quando não confere.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging

from fastapi import Request

from mplacas.core.config import Settings

logger = logging.getLogger(__name__)

CLIENT_IP_HEADER = "X-Mplacas-Client-IP"
PROXY_SECRET_HEADER = "X-Mplacas-Proxy-Secret"


def _secret_matches(presented: str, expected: str) -> bool:
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def resolve_client_ip(request: Request, settings: Settings) -> str | None:
    fallback = request.client.host if request.client else None
    secret = settings.proxy_shared_secret
    if secret is None:
        return fallback
    presented = request.headers.get(PROXY_SECRET_HEADER)
    if presented is None:
        return fallback
    if not _secret_matches(presented, secret.get_secret_value()):
        # Só o fato é registrado; nem o valor apresentado nem o esperado.
        logger.warning("proxy_shared_secret_mismatch", extra={"path": request.url.path})
        return fallback
    raw_ip = request.headers.get(CLIENT_IP_HEADER)
    if raw_ip is None:
        return fallback
    try:
        return str(ipaddress.ip_address(raw_ip.strip()))
    except ValueError:
        return fallback
