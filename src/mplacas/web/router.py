from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from mplacas.core.config import get_settings

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", include_in_schema=False)
async def dashboard() -> RedirectResponse:
    """Compatibilidade sem servir o cliente legado nem receber chave operacional."""
    return RedirectResponse(str(get_settings().dashboard_url), status_code=308)
