"""Painel do investidor: rota (`/energy/investor/latest`) e serviço (ADR-079)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.intelligence.investor_service as investor_service
import mplacas.intelligence.router as intelligence_router
import mplacas.market.service as market_service
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.intelligence.investor_metrics import add_months
from mplacas.intelligence.investor_service import InvestorUnavailableReason, get_investor_panel
from mplacas.main import app
from mplacas.market.db_models import MarketIndexMonthlyRecord
from mplacas.organizations.db_models import OrganizationRecord

PLANT = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
TODAY = date(2026, 10, 19)


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(factory, **plant_fields) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as session:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(id=org_a, name="A", slug=f"a-{org_a.hex[:8]}", active=True),
                OrganizationRecord(id=org_b, name="B", slug=f"b-{org_b.hex[:8]}", active=True),
            ]
        )
        session.add(Plant(id=PLANT, organization_id=org_a, name="Casa", **plant_fields))
        # 14 meses de CDI (1,1% a.m.) e IPCA (0,4% a.m.) já guardados.
        for k in range(0, 15):
            month = add_months("2025-08", k)
            session.add_all(
                [
                    MarketIndexMonthlyRecord(
                        index_code="CDI",
                        reference_month=month,
                        rate_percent=Decimal("1.1"),
                        source="TEST",
                    ),
                    MarketIndexMonthlyRecord(
                        index_code="IPCA",
                        reference_month=month,
                        rate_percent=Decimal("0.4"),
                        source="TEST",
                    ),
                ]
            )
        await session.commit()
        return org_a, org_b


def _snapshot(month: str, savings: str, version: str = "0.3.0") -> SimpleNamespace:
    return SimpleNamespace(
        report=SimpleNamespace(
            reference_month=month,
            calculation_version=version,
            metrics=(SimpleNamespace(key="estimated_savings_brl", value=savings),),
        )
    )


class _FakeSnapshots:
    items: tuple = ()

    def __init__(self, session, plant_scope=None) -> None:
        pass

    async def list_for_plant(self, *, plant_id):
        return type(self).items


@pytest.fixture(autouse=True)
def _reset_market_throttle():
    market_service._last_attempt.clear()


def test_service_returns_realized_and_projection_with_coverage_flags(monkeypatch) -> None:
    factory, engine = asyncio.run(_factory())
    asyncio.run(
        _seed(
            factory,
            investment_amount_brl=Decimal("11200.00"),
            commissioned_on=date(2025, 9, 1),
        )
    )
    _FakeSnapshots.items = (_snapshot("2026-08", "250.00", "0.2.0"), _snapshot("2026-09", "264.00"))
    monkeypatch.setattr(investor_service, "MonthlyReportSnapshotRepository", _FakeSnapshots)

    async def run():
        async with factory() as session:
            return await get_investor_panel(session, plant_id=PLANT, today=TODAY, bcb_client=None)

    panel = asyncio.run(run())
    asyncio.run(engine.dispose())

    assert panel.unavailable_reason is None
    assert panel.cycles_counted == 2
    assert panel.calculation_versions == ("0.2.0", "0.3.0")
    assert panel.includes_pre_correction_cycles is True
    assert panel.low_confidence_baseline is True
    assert panel.indices_as_of_month == "2026-09"
    assert panel.realized is not None
    assert panel.realized.months_elapsed == 12
    assert panel.realized.accumulated_savings_brl == Decimal("514.00")
    assert panel.projection is not None
    assert panel.projection.wire_b_applied is False  # sem fatura confirmada com Fio B
    assert panel.projection.irr_per_year is not None
    # CDI de 12 meses a 1,1% a.m. = 14,03% a.a.
    assert panel.cdi_12m_per_year == Decimal("0.1403")


@pytest.mark.parametrize(
    ("plant_fields", "reason"),
    [
        ({}, InvestorUnavailableReason.INVESTMENT_NOT_REGISTERED),
        (
            {"investment_amount_brl": Decimal("11200.00")},
            InvestorUnavailableReason.COMMISSIONING_DATE_MISSING,
        ),
        (
            {"investment_amount_brl": Decimal("11200.00"), "commissioned_on": date(2025, 9, 1)},
            InvestorUnavailableReason.NO_CONSOLIDATED_SAVINGS,
        ),
    ],
)
def test_service_explains_what_is_missing(monkeypatch, plant_fields, reason) -> None:
    factory, engine = asyncio.run(_factory())
    asyncio.run(_seed(factory, **plant_fields))
    _FakeSnapshots.items = ()
    monkeypatch.setattr(investor_service, "MonthlyReportSnapshotRepository", _FakeSnapshots)

    async def run():
        async with factory() as session:
            return await get_investor_panel(session, plant_id=PLANT, today=TODAY, bcb_client=None)

    panel = asyncio.run(run())
    asyncio.run(engine.dispose())
    assert panel.unavailable_reason == reason
    assert panel.projection is None and panel.realized is None


def test_route_is_tenant_scoped_and_serializes_unavailable_state(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    # Host do BCB fora da lista: a rota nunca sai para a rede, só usa o banco.
    monkeypatch.setenv("MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS", "api.nepviewer.net")
    get_settings.cache_clear()
    factory, engine = asyncio.run(_factory())
    org_a, org_b = asyncio.run(_seed(factory))
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(intelligence_router, "SessionFactory", factory)
    token_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    with TestClient(app) as client:
        own = client.get(
            f"/energy/investor/latest?plant_id={PLANT}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        foreign = client.get(
            f"/energy/investor/latest?plant_id={PLANT}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

    asyncio.run(engine.dispose())
    get_settings.cache_clear()
    assert own.status_code == 200
    body = own.json()
    assert body["unavailable_reason"] == "INVESTMENT_NOT_REGISTERED"
    assert body["projection"] is None
    assert body["indices"]["source"].startswith("Banco Central")
    assert foreign.status_code == 404
