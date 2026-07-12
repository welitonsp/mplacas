from fastapi import FastAPI

from mplacas import __version__
from mplacas.core.config import get_settings

app = FastAPI(
    title="Mplacas API",
    version=__version__,
    description="Inteligência, auditoria e gestão energética residencial.",
)


@app.get("/health", tags=["operational"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mplacas", "version": __version__}


@app.get("/ready", tags=["operational"])
async def ready() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ready",
        "environment": settings.env,
        "nepviewer_configured": settings.nep_configured,
        "timezone": settings.timezone,
    }
