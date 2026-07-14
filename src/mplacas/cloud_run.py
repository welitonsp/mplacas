from __future__ import annotations

import logging

import uvicorn

from mplacas.core.config import get_settings


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    uvicorn.run(
        "mplacas.main:app",
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
