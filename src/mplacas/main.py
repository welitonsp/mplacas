from fastapi import FastAPI
from sqlalchemy import text

from mplacas import __version__
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory

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
    database_ready = False
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        database_ready = True
    except Exception:
        database_ready = False

    status = "ready" if database_ready else "degraded"
    return {
        "status": status,
        "environment": settings.env,
        "database_ready": database_ready,
        "nepviewer_configured": settings.nep_configured,
        "timezone": settings.timezone,
    }
