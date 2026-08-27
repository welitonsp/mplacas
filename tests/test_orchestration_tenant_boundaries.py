"""PR-4: cross-tenant boundary tests for ``orchestration.router``.

Verifies that a caller authenticated for organization B receives 404 (not
403 — same convention as PR-2/PR-3) when trying to operate on organization
A's plant, on every handler in the router: ``/pipeline/run`` and
``/pipeline/status/latest``.

``/pipeline/run`` triggers a real Telegram alert dispatch as a side effect of
running the daily pipeline, so the negative-proof assertion below stubs the
pipeline runtime to raise if it is ever invoked — the same pattern used by
``test_billing_tenant_boundaries``'s ``/intake-text`` test and by
``test_alerts_tenant_boundaries``'s ``/alerts/run`` test.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.orchestration.router as orchestration_router
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000d1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID]:
    """Create org A (with plant A) and org B (no plants)."""
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a, name="Org A", slug=f"org-a-{org_a.hex[:8]}", active=True
                ),
                OrganizationRecord(
                    id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:8]}", active=True
                ),
            ]
        )
        session.add(Plant(id=PLANT_A, organization_id=org_a, name="Plant A"))
        await session.commit()
        return org_a, org_b


@pytest.fixture
def cross_tenant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(orchestration_router, "SessionFactory", factory)

    org_a, org_b = asyncio.run(_seed(factory))
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield org_a, org_b, token_b

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def test_pipeline_run_cross_tenant_is_not_found_and_never_dispatches(
    cross_tenant_setup, monkeypatch
) -> None:
    _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    async def fake_runtime(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError(
            "pipeline runtime should not run before plant scope is validated"
        )

    monkeypatch.setattr(
        orchestration_router, "run_ledger_backed_daily_pipeline", fake_runtime
    )

    response = client.post(
        "/pipeline/run",
        headers={"Authorization": f"Bearer {token_b}"},
        params={
            "plant_id": str(PLANT_A),
            "target_date": "2026-07-13",
            "expected_daily_production_kwh": "10",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_pipeline_status_latest_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    """Before PR-4, ``/pipeline/status/latest`` had no plant validation at all
    (not even a 404) beyond authentication via the router-level
    ``require_operations_key`` dependency — org B could read org A's pipeline
    execution status outright. This asserts the fix: org B is rejected with
    404 before the lookup runs.
    """
    _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.get(
        "/pipeline/status/latest",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
