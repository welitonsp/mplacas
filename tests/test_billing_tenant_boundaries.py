"""PR-3: cross-tenant boundary tests for ``billing.router``.

Verifies that a caller authenticated for organization B receives 404 (not
403 — same convention as PR-2, so the response does not reveal the existence
of a plant the caller has no access to) when trying to operate on organization
A's plant or bills, on every handler in the router: ``/intake-text``,
``/pending``, ``/{bill_id}/confirm`` and ``/{bill_id}/reject``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.billing.router as billing_router
from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000b1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create org A (with plant A + a pending bill) and org B (no plants)."""
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
        bill = UtilityBillRecord(
            id=uuid.uuid4(),
            plant_id=PLANT_A,
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 5, 18),
            cycle_end=date(2026, 6, 16),
            billed_days=30,
            imported_kwh=Decimal("278.000"),
            injected_kwh=Decimal("182.000"),
            compensated_kwh=Decimal("278.000"),
            credit_balance_kwh=Decimal("63.980"),
            total_amount_brl=Decimal("80.21"),
            public_lighting_brl=Decimal("30.21"),
            status=BillStatus.PENDING_REVIEW,
            source_hash="cross-tenant-fixture-hash",
        )
        session.add(bill)
        await session.flush()
        await session.commit()
        return org_a, org_b, bill.id


@pytest.fixture
def cross_tenant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(billing_router, "SessionFactory", factory)

    org_a, org_b, bill_id = asyncio.run(_seed(factory))
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield org_a, org_b, bill_id, token_b

    get_settings.cache_clear()


def test_intake_text_cross_tenant_is_not_found(cross_tenant_setup, monkeypatch) -> None:
    _, _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    # Cross-tenant validation must reject the request before the bill text is
    # ever parsed, so the parser's own success/failure is irrelevant here —
    # stub it out to isolate the tenancy check being exercised.
    def fake_parse(text: str):  # pragma: no cover - should never be reached
        raise AssertionError("parser should not run before plant scope is validated")

    monkeypatch.setattr(billing_router, "parse_equatorial_bill_text", fake_parse)

    response = client.post(
        "/billing/intake-text",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "plant_id": str(PLANT_A),
            "text": "org b trying to intake a bill for org a's plant, padded",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_pending_bills_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.get(
        "/billing/pending",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_confirm_bill_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, bill_id, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.post(
        f"/billing/{bill_id}/confirm",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_reject_bill_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, bill_id, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.post(
        f"/billing/{bill_id}/reject",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
