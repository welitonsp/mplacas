from __future__ import annotations

import logging
import os
from typing import Any

import uvicorn
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from mplacas.core.client_ip import RestoreTcpPeerMiddleware, TcpPeerMiddleware
from mplacas.core.config import Settings, get_settings
from mplacas.observability.tracing import configure_observability

logger = logging.getLogger(__name__)


def build_asgi_app(app: Any, settings: Settings) -> Any:
    """Monta a cadeia de cabeçalhos de proxy (ADR-102 § 6).

    O ``ProxyHeadersMiddleware`` é aplicado aqui, e não pelo ``uvicorn.run``,
    para que ``TcpPeerMiddleware`` fique POR FORA dele e guarde o par TCP real
    (usado pelo modo ``TRUSTED_PROXY_HOPS`` e pelo ``client_ip_diagnostic``).
    Sem ``trusted_proxy_hops``, o comportamento é o mesmo de antes
    (``proxy_headers=True`` com ``forwarded_allow_ips`` da config).
    """
    inner: Any = (
        RestoreTcpPeerMiddleware(app) if settings.trusted_proxy_hops is not None else app
    )
    return TcpPeerMiddleware(
        ProxyHeadersMiddleware(inner, trusted_hosts=settings.forwarded_allow_ips)
    )


def _warn_blank_proxy_secret() -> None:
    raw = os.environ.get("MPLACAS_PROXY_SHARED_SECRET")
    if raw is not None and not raw.strip():
        # Em branco vale como "não configurado" — o cabeçalho do proxy é
        # ignorado. Avisa para não parecer que o proxy está autenticado.
        logger.warning("proxy_shared_secret_blank_ignored")


def main() -> int:
    settings = get_settings()
    _warn_blank_proxy_secret()
    from mplacas.db.session import engine
    from mplacas.main import app

    observability = configure_observability(
        settings=settings,
        service_name="mplacas-api",
        app=app,
        engine=engine,
    )
    try:
        uvicorn.run(
            build_asgi_app(app, settings),
            host="0.0.0.0",
            port=settings.port,
            # Os cabeçalhos de proxy já são tratados em ``build_asgi_app``.
            proxy_headers=False,
            log_level=settings.log_level.lower(),
            log_config=None,
            access_log=False,
        )
    finally:
        observability.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
