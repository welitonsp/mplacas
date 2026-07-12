from fastapi import FastAPI
from sqlalchemy import text

from mplacas import __version__
from mplacas.billing.router import router as billing_router
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory
from mplacas.operations.router import router as operations_router
from mplacas.telegram.router import router as telegram_router

app = FastAPI(
    title="Mplacas API",
    version=__version__,
    description="Inteligência, auditoria e gestão energética residencial.",
)
app.include_router(operations_router)
app.include_router(billing_router)
app.include_router(telegram_router)


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
        "telegram_configured": settings.telegram_configured,
        "operational_auth_configured": settings.operations_api_key is not None,
        "timezone": settings.timezone,
    }
