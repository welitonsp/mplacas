from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.core.config import get_settings
from mplacas.main import app
import mplacas.explanations.router as explanations_router


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def test_explanation_endpoint_is_protected_and_falls_back_deterministically(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    monkeypatch.delenv("MPLACAS_EXPLANATION_API_URL", raising=False)
    get_settings.cache_clear()
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000028")

    dashboard = SimpleNamespace(
        plant_id=plant_id,
        status=SimpleNamespace(value="ATTENTION"),
        headline="Synthetic cycle requires monitoring.",
        current_cycle=SimpleNamespace(
            intelligence=SimpleNamespace(
                diagnostics=(
                    SimpleNamespace(
                        code="LOW_SELF_CONSUMPTION",
                        severity=SimpleNamespace(value="WARNING"),
                        message="Self-consumption is below the threshold.",
                        recommended_action="Review daytime load distribution.",
                    ),
                )
            )
        ),
    )

    async def fake_dashboard(*args, **kwargs):
        return dashboard

    monkeypatch.setattr(explanations_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(explanations_router, "build_executive_dashboard", fake_dashboard)

    client = TestClient(app)
    unauthorized = client.get(
        "/energy/explanations/latest",
        params={"plant_id": str(plant_id)},
    )
    assert unauthorized.status_code == 401

    response = client.get(
        "/energy/explanations/latest",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "DETERMINISTIC"
    assert payload["status"] == "ATTENTION"
    assert payload["evidence_codes"] == ["LOW_SELF_CONSUMPTION"]
    assert "não confirma causa técnica" in payload["disclaimer"]
    get_settings.cache_clear()
