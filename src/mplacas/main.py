import asyncio
import logging
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
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
from mplacas.reports.router import router as reports_router
from mplacas.telegram.router import router as telegram_router
from mplacas.web.router import router as web_router

logger = logging.getLogger(__name__)
_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 128


def _normalize_request_id(value: str | None) -> str:
    if value is None:
        return uuid4().hex
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_REQUEST_ID_LENGTH:
        return uuid4().hex
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")
    if any(character not in allowed for character in cleaned):
        return uuid4().hex
    return cleaned


app = FastAPI(
    title="Mplacas API",
    version=__version__,
    description="Inteligência, auditoria e gestão energética residencial.",
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = _normalize_request_id(request.headers.get(_REQUEST_ID_HEADER))
    request.state.request_id = request_id
    started = monotonic()
    response = await call_next(request)
    duration_ms = max(0, round((monotonic() - started) * 1000))
    response.headers[_REQUEST_ID_HEADER] = request_id
    principal = getattr(request.state, "operations_principal", None)
    audit_fields: dict[str, object] = {}
    if principal is not None:
        audit_fields = {
            "operations_role": principal.role.value,
            "operations_credential_id": principal.credential_id,
            "operations_plant_scope": (
                "restricted" if principal.plant_scope.is_restricted else "unrestricted"
            ),
            "operations_plant_count": len(principal.plant_scope.plant_ids or ()),
        }
    logger.info(
        "http_request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            **audit_fields,
        },
    )
    return response


app.include_router(operations_router)
app.include_router(billing_router)
app.include_router(telegram_router)
app.include_router(intelligence_router)
app.include_router(explanations_router)
app.include_router(alerts_router)
app.include_router(climate_router)
app.include_router(orchestration_router)
app.include_router(reports_router)
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
async def ready(response: Response) -> dict[str, object]:
    try:
        settings = get_settings()
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "configuration_valid": False,
            "database_ready": False,
        }

    database_ready = False
    try:
        async with SessionFactory() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")),
                timeout=settings.readiness_timeout_seconds,
            )
        database_ready = True
    except TimeoutError:
        database_ready = False
    except Exception:
        database_ready = False

    if not database_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    ready_status = "ready" if database_ready else "degraded"
    return {
        "status": ready_status,
        "configuration_valid": True,
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
