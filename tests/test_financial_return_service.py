"""Tests for `GET /energy/financial-return/latest` (ADR-067, Etapa D).

Follows the same in-memory-sqlite + JWT pattern used by
``test_plants_router.py`` and the tenant-boundary rigor of
``test_photovoltaic_tenant_boundaries.py``: real database round-trips, not
mocked sessions or services.

Snapshots are inserted directly as ``MonthlyReportSnapshotRecord`` rows with
a hand-built ``payload_json``/``payload_sha256`` pair (same technique as
``tests/test_report_projection_savings.py::test_legacy_snapshot_...``),
because the financial-return indicator must read *only* from persisted,
immutable snapshots — never recompute from ``utility_bills`` (ADR-067,
item 6).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.intelligence.router as intelligence_router
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.reports.db_models import MonthlyReportSnapshotRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(
    factory,
    *,
    investment_amount_brl: Decimal | None = None,
    investment_recorded_on: date | None = None,
    commissioned_on: date | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
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
        plant = Plant(
            id=PLANT_A,
            organization_id=org_a,
            name="Plant A",
            investment_amount_brl=investment_amount_brl,
            investment_recorded_on=investment_recorded_on,
            commissioned_on=commissioned_on,
        )
        session.add(plant)
        await session.commit()
        return org_a, org_b


def _snapshot_payload_json(
    *,
    plant_id: uuid.UUID,
    bill_id: uuid.UUID,
    reference_month: str,
    savings_value: str | None,
    include_savings_metric: bool = True,
) -> str:
    """Build a snapshot payload with (or without) the savings metric.

    ``savings_value=None`` with ``include_savings_metric=True`` reproduces a
    snapshot emitted after Etapa A where the economy could not be computed
    (empty value, motivo separado). ``include_savings_metric=False``
    reproduces a snapshot emitted *before* Etapa A, where the metric simply
    does not exist in the payload.
    """
    metrics = []
    if include_savings_metric:
        metrics.append(
            {
                "key": "estimated_savings_brl",
                "label": "Economia estimada",
                "value": savings_value if savings_value is not None else "",
                "unit": "BRL",
                "nature": "CALCULATED",
                "source": "MPLACAS_DETERMINISTIC_ENGINE",
            }
        )
    payload = {
        "schema_version": "1.0",
        "calculation_version": "0.9.0",
        "plant_id": str(plant_id),
        "bill_id": str(bill_id),
        "reference_month": reference_month,
        "status": "HEALTHY",
        "headline": "Ciclo sintético dentro dos parâmetros avaliados.",
        "metrics": metrics,
        "quality": [],
        "diagnostics": [],
        "priority_actions": [],
        "trend": None,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def _add_snapshot(
    factory,
    *,
    plant_id: uuid.UUID,
    reference_month: str,
    savings_value: str | None,
    include_savings_metric: bool = True,
) -> None:
    bill_id = uuid.uuid4()
    payload_json = _snapshot_payload_json(
        plant_id=plant_id,
        bill_id=bill_id,
        reference_month=reference_month,
        savings_value=savings_value,
        include_savings_metric=include_savings_metric,
    )
    payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    async with factory() as session:
        session.add(
            MonthlyReportSnapshotRecord(
                plant_id=plant_id,
                bill_id=bill_id,
                reference_month=reference_month,
                schema_version="1.0",
                calculation_version="0.9.0",
                payload_json=payload_json,
                payload_sha256=payload_sha256,
            )
        )
        await session.commit()


@pytest.fixture
def tenancy_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(intelligence_router, "SessionFactory", factory)

    yield factory

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _tokens(org_a: uuid.UUID, org_b: uuid.UUID) -> tuple[str, str]:
    token_a_read = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    token_b_read = encode_access_token(uuid.uuid4(), org_b, OperationsRole.READ.value)
    return token_a_read, token_b_read


@pytest.fixture
def client(tenancy_setup):
    with TestClient(app) as test_client:
        yield test_client


async def _count_snapshots(factory) -> int:
    async with factory() as session:
        result = await session.execute(select(MonthlyReportSnapshotRecord))
        return len(list(result.scalars()))


def test_investment_not_registered_yields_all_null_derived_fields(
    tenancy_setup, client: TestClient
) -> None:
    factory = tenancy_setup
    org_a, org_b = asyncio.run(_seed(factory, investment_amount_brl=None))
    token_a_read, _ = _tokens(org_a, org_b)

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plant_id"] == str(PLANT_A)
    assert body["investment_amount_brl"] is None
    assert body["unavailable_reason"] == "INVESTMENT_NOT_REGISTERED"
    assert body["payback_unavailable_reason"] is None
    for field in (
        "accumulated_savings_brl",
        "average_monthly_savings_brl",
        "cycles_counted",
        "cycles_expected",
        "roi_percent",
        "payback_projection_months",
    ):
        assert body[field] is None, field


def test_no_consolidated_savings_when_investment_registered_but_no_metrics(
    tenancy_setup, client: TestClient
) -> None:
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("48000.00"),
            commissioned_on=date(2024, 3, 1),
        )
    )
    token_a_read, _ = _tokens(org_a, org_b)
    # A single legacy snapshot, pre-Etapa-A: no metric at all.
    asyncio.run(
        _add_snapshot(
            factory,
            plant_id=PLANT_A,
            reference_month="2024-04",
            savings_value=None,
            include_savings_metric=False,
        )
    )

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["investment_amount_brl"] == "48000.00"
    assert body["unavailable_reason"] == "NO_CONSOLIDATED_SAVINGS"
    assert body["payback_unavailable_reason"] is None
    assert body["cycles_counted"] == 0
    # cycles_expected still computed: it does not depend on the metric.
    assert body["cycles_expected"] == 2
    for field in (
        "accumulated_savings_brl",
        "average_monthly_savings_brl",
        "roi_percent",
        "payback_projection_months",
    ):
        assert body[field] is None, field
        assert body[field] != "0.00"
        assert body[field] != 0


def test_insufficient_history_still_shows_roi_only_hides_payback(
    tenancy_setup, client: TestClient
) -> None:
    """The case most likely to be broken: ROI is valid with < 6 cycles, but
    the payback projection alone must be unavailable (ADR-067, Decisão item
    5 — the whole reason the two reason fields are kept separate)."""
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("10000.00"),
            commissioned_on=date(2024, 1, 1),
        )
    )
    token_a_read, _ = _tokens(org_a, org_b)
    for index, month in enumerate(("2024-01", "2024-02", "2024-03"), start=1):
        asyncio.run(
            _add_snapshot(
                factory,
                plant_id=PLANT_A,
                reference_month=month,
                savings_value="100.00",
            )
        )

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["unavailable_reason"] is None
    assert body["cycles_counted"] == 3
    assert body["accumulated_savings_brl"] == "300.00"
    assert body["average_monthly_savings_brl"] == "100.00"
    assert body["roi_percent"] == "3.0"
    assert body["payback_unavailable_reason"] == "INSUFFICIENT_HISTORY"
    assert body["payback_projection_months"] is None


def test_partial_coverage_ignores_legacy_snapshots_but_still_computes(
    tenancy_setup, client: TestClient
) -> None:
    """Cycles_expected reflects the full commissioned history, while
    cycles_counted only reflects snapshots carrying the metric — legacy
    (pre-Etapa-A) snapshots are silently skipped, never breaking the sum."""
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("6000.00"),
            commissioned_on=date(2024, 1, 1),
        )
    )
    token_a_read, _ = _tokens(org_a, org_b)

    # Two legacy months (no metric at all) followed by six months with the
    # metric present -> 8 months of reference history, but only 6 counted.
    asyncio.run(
        _add_snapshot(
            factory,
            plant_id=PLANT_A,
            reference_month="2024-01",
            savings_value=None,
            include_savings_metric=False,
        )
    )
    asyncio.run(
        _add_snapshot(
            factory,
            plant_id=PLANT_A,
            reference_month="2024-02",
            savings_value=None,
            include_savings_metric=False,
        )
    )
    for month in ("2024-03", "2024-04", "2024-05", "2024-06", "2024-07", "2024-08"):
        asyncio.run(
            _add_snapshot(
                factory,
                plant_id=PLANT_A,
                reference_month=month,
                savings_value="100.00",
            )
        )

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles_counted"] == 6
    assert body["cycles_expected"] == 8
    assert body["cycles_counted"] < body["cycles_expected"]
    assert body["accumulated_savings_brl"] == "600.00"
    assert body["unavailable_reason"] is None


def test_payback_already_reached_returns_cycles_counted(
    tenancy_setup, client: TestClient
) -> None:
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("600.00"),
            commissioned_on=date(2024, 1, 1),
        )
    )
    token_a_read, _ = _tokens(org_a, org_b)
    for month in ("2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"):
        asyncio.run(
            _add_snapshot(
                factory,
                plant_id=PLANT_A,
                reference_month=month,
                savings_value="100.00",
            )
        )

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles_counted"] == 6
    assert body["accumulated_savings_brl"] == "600.00"
    assert body["roi_percent"] == "100.0"
    assert body["payback_unavailable_reason"] is None
    assert body["payback_projection_months"] == 6


def test_full_response_matches_expected_shape_with_healthy_coverage(
    tenancy_setup, client: TestClient
) -> None:
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("1000.00"),
            investment_recorded_on=date(2024, 3, 11),
            commissioned_on=date(2024, 1, 1),
        )
    )
    token_a_read, _ = _tokens(org_a, org_b)
    for month in (
        "2024-01",
        "2024-02",
        "2024-03",
        "2024-04",
        "2024-05",
        "2024-06",
        "2024-07",
    ):
        asyncio.run(
            _add_snapshot(
                factory,
                plant_id=PLANT_A,
                reference_month=month,
                savings_value="50.00",
            )
        )

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "plant_id": str(PLANT_A),
        "investment_amount_brl": "1000.00",
        "investment_recorded_on": "2024-03-11",
        "commissioned_on": "2024-01-01",
        "accumulated_savings_brl": "350.00",
        "average_monthly_savings_brl": "50.00",
        "cycles_counted": 7,
        "cycles_expected": 7,
        "roi_percent": "35.0",
        "payback_projection_months": 20,
        "unavailable_reason": None,
        "payback_unavailable_reason": None,
    }


def test_cross_tenant_plant_returns_404(tenancy_setup, client: TestClient) -> None:
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(factory, investment_amount_brl=Decimal("1000.00"))
    )
    _, token_b_read = _tokens(org_a, org_b)

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_b_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_endpoint_never_writes_to_the_database(tenancy_setup, client: TestClient) -> None:
    """A GET must never materialize a snapshot (ADR-067, item 6)."""
    factory = tenancy_setup
    org_a, org_b = asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("1000.00"),
            commissioned_on=date(2024, 1, 1),
        )
    )
    token_a_read, _ = _tokens(org_a, org_b)
    before = asyncio.run(_count_snapshots(factory))
    assert before == 0

    response = client.get(
        "/energy/financial-return/latest",
        headers={"Authorization": f"Bearer {token_a_read}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    assert response.json()["unavailable_reason"] == "NO_CONSOLIDATED_SAVINGS"
    after = asyncio.run(_count_snapshots(factory))
    assert after == 0
