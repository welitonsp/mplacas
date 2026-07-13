from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from mplacas import __version__
from mplacas.alerts.router import router as alerts_router
from mplacas.billing.router import router as billing_router
from mplacas.climate.router import router as climate_router
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory
from mplacas.explanations.router import router as explanations_router
from mplacas.intelligence.router import router as intelligence_router
from mplacas.operations.router import router as operations_router
from mplacas.orchestration.router import router as orchestration_router
from mplacas.telegram.router import router as telegram_router
from mplacas.web.router import router as web_router

app = FastAPI(
    title="Mplacas API",
    version=__version__,
    description="Inteligência, auditoria e gestão energética residencial.",
)
app.include_router(operations_router)
app.include_router(billing_router)
app.include_router(telegram_router)
app.include_router(intelligence_router)
app.include_router(explanations_router)
app.include_router(alerts_router)
app.include_router(climate_router)
app.include_router(orchestration_router)
app.include_router(web_router)
app.mount(
    "/dashboard-assets",
    StaticFiles(directory=Path(__file__).parent / "web" / "static"),
    name="dashboard-assets",
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
        "telegram_configured": settings.telegram_configured,
        "telegram_alerts_configured": settings.telegram_alerts_configured,
        "climate_provider_configured": bool(settings.climate_archive_base_url),
        "pipeline_runtime_configured": settings.pipeline_stale_lock_timeout_minutes > 0,
        "explanation_provider_configured": settings.explanation_provider_configured,
        "operational_auth_configured": settings.operations_api_key is not None,
        "timezone": settings.timezone,
    }
