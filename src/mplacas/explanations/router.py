from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from mplacas.core.config import get_settings
from mplacas.core.security import OperationsPrincipal, require_operations_read
from mplacas.db.session import SessionFactory
from mplacas.explanations.executive import executive_explanation_request
from mplacas.explanations.http_provider import StructuredHttpExplanationProvider
from mplacas.explanations.provider import ExplanationProvider
from mplacas.explanations.service import explain_with_fallback
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError
from mplacas.intelligence.executive_service import build_executive_dashboard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/energy/explanations",
    tags=["explanations"],
)


@router.get("/latest", status_code=status.HTTP_200_OK)
async def latest_explanation(
    principal: Annotated[OperationsPrincipal, Depends(require_operations_read)],
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = Query(default=None, gt=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0),
) -> dict[str, object]:
    principal.require_plant_access(plant_id)
    settings = get_settings()
    provider: ExplanationProvider | None = None
    if settings.explanation_api_url is not None:
        provider = StructuredHttpExplanationProvider(
            endpoint_url=str(settings.explanation_api_url),
            timeout_seconds=settings.explanation_timeout_seconds,
            api_key=(
                settings.explanation_api_key.get_secret_value()
                if settings.explanation_api_key is not None
                else None
            ),
            model=settings.explanation_model,
        )

    try:
        async with SessionFactory() as session:
            dashboard = await build_executive_dashboard(
                session,
                plant_id=plant_id,
                expected_production_kwh=expected_production_kwh,
                stable_tolerance_percent=stable_tolerance_percent,
                plant_scope=principal.plant_scope,
            )
    except EnergyCycleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    request = executive_explanation_request(dashboard)
    explanation = await explain_with_fallback(request, provider=provider)
    logger.info(
        "grounded_explanation_completed",
        extra={
            "plant_id": str(plant_id),
            "source": explanation.source.value,
            "evidence_count": len(request.evidence),
        },
    )
    return {
        "plant_id": str(plant_id),
        "status": dashboard.status.value,
        "source": explanation.source.value,
        "summary": explanation.summary,
        "what_it_means": explanation.what_it_means,
        "next_steps": list(explanation.next_steps),
        "disclaimer": explanation.disclaimer,
        "evidence_codes": [item.code for item in request.evidence],
    }
