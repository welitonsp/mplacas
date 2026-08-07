"""Tests for ``GET /reports/monthly/history`` and
``MonthlyReportSnapshotRepository.list_recent_for_plant``.

Covers the contract from the "produção por ciclo" chart spec: bounded,
chronologically-ordered history of already-materialized snapshots, never
materializing anything new, and respecting tenant boundaries the same way
every other read endpoint in this project does.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.reports.router as reports_router
from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.reports.db_models import MonthlyReportSnapshotRecord
from mplacas.reports.snapshot import MonthlyReportSnapshotRepository

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000f1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _bill(*, plant_id: uuid.UUID, reference_month: str, source_hash: str) -> UtilityBillRecord:
    cycle_day = date(2026, int(reference_month.split("-")[1]), 28)
    return UtilityBillRecord(
        plant_id=plant_id,
        distributor="EQUATORIAL_GO",
        reference_month=reference_month,
        cycle_start=cycle_day,
        cycle_end=cycle_day,
        billed_days=1,
        imported_kwh=Decimal("20"),
        injected_kwh=Decimal("40"),
        compensated_kwh=Decimal("20"),
        credit_balance_kwh=Decimal("50"),
        total_amount_brl=Decimal("60"),
        public_lighting_brl=Decimal("30"),
        status=BillStatus.CONFIRMED,
        source_hash=source_hash,
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _payload(
    *,
    plant_id: uuid.UUID,
    bill_id: uuid.UUID,
    reference_month: str,
    production_kwh: str | None,
    quality: dict[str, str] | None,
) -> str:
    quality_items = []
    if quality is not None:
        for key, value in quality.items():
            quality_items.append(
                {
                    "key": key,
                    "label": key,
                    "value": value,
                    "unit": "days",
                    "nature": "QUALITY_COUNT",
                    "source": "MPLACAS_DETERMINISTIC_ENGINE",
                }
            )
    metrics = [
        {
            "key": "cycle_production_kwh",
            "label": "Produção do ciclo",
            "value": "" if production_kwh is None else production_kwh,
            "unit": "kWh",
            "nature": "MEASURED_AGGREGATE",
            "source": "DAILY_ENERGY_AGGREGATE",
        }
    ]
    payload = {
        "schema_version": "1.0",
        "calculation_version": "0.2.0",
        "plant_id": str(plant_id),
        "bill_id": str(bill_id),
        "reference_month": reference_month,
        "status": "HEALTHY",
        "headline": "Ciclo sintético.",
        "metrics": metrics,
        "quality": quality_items,
        "diagnostics": [],
        "priority_actions": [],
        "trend": None,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_record(
    *,
    plant_id: uuid.UUID,
    bill_id: uuid.UUID,
    reference_month: str,
    production_kwh: str | None = "100.000",
    quality: dict[str, str] | None = None,
) -> MonthlyReportSnapshotRecord:
    if quality is None:
        quality = {
            "missing_days": "0",
            "provisional_days": "0",
            "incomplete_days": "0",
            "unavailable_days": "0",
        }
    payload_json = _payload(
        plant_id=plant_id,
        bill_id=bill_id,
        reference_month=reference_month,
        production_kwh=production_kwh,
        quality=quality,
    )
    return MonthlyReportSnapshotRecord(
        plant_id=plant_id,
        bill_id=bill_id,
        reference_month=reference_month,
        schema_version="1.0",
        calculation_version="0.2.0",
        payload_json=payload_json,
        payload_sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
    )


async def _seed_cycles(
    factory, *, plant_id: uuid.UUID, months: list[str], **snapshot_kwargs
) -> None:
    async with factory() as session:
        for index, month in enumerate(months):
            bill = _bill(plant_id=plant_id, reference_month=month, source_hash=f"{index}" * 64)
            session.add(bill)
            await session.flush()
            session.add(
                _snapshot_record(
                    plant_id=plant_id,
                    bill_id=bill.id,
                    reference_month=month,
                    **snapshot_kwargs,
                )
            )
        await session.commit()


@pytest.fixture
def cross_tenant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(reports_router, "SessionFactory", factory)

    async def _seed_org() -> tuple[uuid.UUID, uuid.UUID]:
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

    org_a, org_b = asyncio.run(_seed_org())
    token_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield factory, org_a, org_b, token_a, token_b

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_more_cycles_than_limit_returns_most_recent_in_chronological_order(
    cross_tenant_setup,
) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    months = [f"2026-{i:02d}" for i in range(1, 6)]
    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=months))

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A), "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles_returned"] == 3
    assert body["limit"] == 3
    returned_months = [item["reference_month"] for item in body["cycles"]]
    assert returned_months == ["2026-03", "2026-04", "2026-05"]


def test_fewer_cycles_than_limit_returns_all_without_ghost_months(
    cross_tenant_setup,
) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(factory, plant_id=PLANT_A, months=["2026-01", "2026-02"])
    )

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A), "limit": 12},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles_returned"] == 2
    assert [item["reference_month"] for item in body["cycles"]] == ["2026-01", "2026-02"]


def test_no_cycles_returns_empty_list_with_200(cross_tenant_setup) -> None:
    _, _, _, token_a, _ = cross_tenant_setup

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles"] == []
    assert body["cycles_returned"] == 0


def test_missing_production_metric_is_null_not_zero(cross_tenant_setup) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-01"],
            production_kwh=None,
        )
    )

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles_returned"] == 1
    assert body["cycles"][0]["production_kwh"] is None


def test_missing_all_quality_keys_yields_null_quality_object(cross_tenant_setup) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-01"],
            quality={},
        )
    )

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles"][0]["quality"] is None


def test_cross_tenant_caller_does_not_receive_other_org_history(
    cross_tenant_setup,
) -> None:
    factory, _, _, _, token_b = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01", "2026-02"]))

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_b),
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_repository_list_recent_for_plant_returns_empty_outside_scope(
    cross_tenant_setup,
) -> None:
    from mplacas.core.authorization import PlantScope

    factory, _, _, _, _ = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01", "2026-02"]))

    async def _run() -> tuple[int, int]:
        async with factory() as session:
            unrestricted = await MonthlyReportSnapshotRepository(session).list_recent_for_plant(
                plant_id=PLANT_A, limit=12
            )
            other_scope = PlantScope.restricted({uuid.uuid4()})
            restricted = await MonthlyReportSnapshotRepository(
                session, plant_scope=other_scope
            ).list_recent_for_plant(plant_id=PLANT_A, limit=12)
            return len(unrestricted), len(restricted)

    unrestricted_count, restricted_count = asyncio.run(_run())
    assert unrestricted_count == 2
    assert restricted_count == 0


def test_history_route_never_creates_a_snapshot(cross_tenant_setup) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01"]))

    async def _count() -> int:
        async with factory() as session:
            return await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))

    before = asyncio.run(_count())

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 200

    after = asyncio.run(_count())
    assert before == after == 1
