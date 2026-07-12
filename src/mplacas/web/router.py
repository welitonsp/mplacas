from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["dashboard"])
_ASSET_DIR = Path(__file__).parent / "static"


@router.get("/dashboard", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(_ASSET_DIR / "index.html", media_type="text/html")
