from __future__ import annotations

import uvicorn

from mplacas.core.config import get_settings
from mplacas.observability.tracing import configure_observability


def main() -> int:
    settings = get_settings()
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
            app,
            host="0.0.0.0",
            port=settings.port,
            proxy_headers=True,
            forwarded_allow_ips="*",
            log_level=settings.log_level.lower(),
            log_config=None,
            access_log=False,
        )
    finally:
        observability.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
