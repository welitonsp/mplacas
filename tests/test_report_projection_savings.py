"""ADR-067, Etapa A: `estimated_savings_brl` e `savings_unavailable_reason`
passam a ser projetadas como `ReportMetric` no relatório mensal, sem quebrar
snapshots já gravados e sem alterar o hash de payloads existentes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.reports.db_models import MonthlyReportSnapshotRecord
from mplacas.reports.report_projection import project_executive_dashboard
from mplacas.reports.snapshot import MonthlyReportSnapshotRepository


def _dashboard(
    plant_id: uuid.UUID,
    *,
    estimated_savings_brl: Decimal | None,
    savings_unavailable_reason: str | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        plant_id=plant_id,
        status=SimpleNamespace(value="HEALTHY"),
        headline="Ciclo sintético dentro dos parâmetros avaliados.",
        priority_actions=(),
        current_cycle=SimpleNamespace(
            bill_id=uuid.UUID("00000000-0000-0000-0000-000000000200"),
            reference_month="2026-06",
            quality=SimpleNamespace(
                missing_days=0,
                provisional_days=0,
                incomplete_days=0,
                unavailable_days=0,
            ),
            intelligence=SimpleNamespace(
                reconciliation=SimpleNamespace(
                    cycle_production_kwh=Decimal("100.000"),
                    imported_kwh=Decimal("20.000"),
                    injected_kwh=Decimal("40.000"),
                    estimated_self_consumption_kwh=Decimal("60.000"),
                    estimated_total_consumption_kwh=Decimal("80.000"),
                    self_consumption_rate_percent=Decimal("60.0"),
                    self_sufficiency_rate_percent=Decimal("75.0"),
                ),
                grid_dependency_rate_percent=Decimal("25.0"),
                exported_generation_rate_percent=Decimal("40.0"),
                credit_coverage_rate_percent=Decimal("80.0"),
                bill_energy_component_brl=Decimal("45.20"),
                estimated_savings_brl=estimated_savings_brl,
                savings_unavailable_reason=savings_unavailable_reason,
                health_score=97,
                diagnostics=(),
            ),
        ),
        trend=None,
    )


def test_estimated_savings_metric_present_with_value_when_calculated() -> None:
    plant_id = uuid.uuid4()
    dashboard = _dashboard(
        plant_id,
        estimated_savings_brl=Decimal("18.75"),
        savings_unavailable_reason=None,
    )

    report = project_executive_dashboard(dashboard)

    savings = next(item for item in report.metrics if item.key == "estimated_savings_brl")
    reason = next(item for item in report.metrics if item.key == "savings_unavailable_reason")
    assert savings.value == "18.75"
    assert savings.unit == "BRL"
    assert savings.nature == "CALCULATED"
    assert savings.source == "MPLACAS_DETERMINISTIC_ENGINE"
    assert reason.value == ""
    assert reason.unit is None
    assert reason.nature == "UNAVAILABILITY_REASON"


def test_estimated_savings_metric_present_but_empty_when_unavailable() -> None:
    """A métrica de economia não é omitida quando indisponível: ela é projetada
    com valor vazio, e o motivo explícito vem na métrica irmã. Omitir a chave
    tornaria indistinguível de um snapshot antigo sem o conceito (ADR-067)."""
    plant_id = uuid.uuid4()
    dashboard = _dashboard(
        plant_id,
        estimated_savings_brl=None,
        savings_unavailable_reason="TARIFF_NOT_AVAILABLE",
    )

    report = project_executive_dashboard(dashboard)

    keys = [item.key for item in report.metrics]
    assert "estimated_savings_brl" in keys
    assert "savings_unavailable_reason" in keys

    savings = next(item for item in report.metrics if item.key == "estimated_savings_brl")
    reason = next(item for item in report.metrics if item.key == "savings_unavailable_reason")
    assert savings.value == ""
    assert savings.value != "0.00"
    assert savings.value != "0"
    assert reason.value == "TARIFF_NOT_AVAILABLE"


def _legacy_payload_json(*, plant_id: uuid.UUID, bill_id: uuid.UUID) -> str:
    """Payload no formato emitido antes da Etapa A: sem as duas métricas novas."""
    payload = {
        "schema_version": "1.0",
        "calculation_version": "0.2.0",
        "plant_id": str(plant_id),
        "bill_id": str(bill_id),
        "reference_month": "2026-05",
        "status": "HEALTHY",
        "headline": "Ciclo sintético dentro dos parâmetros avaliados.",
        "metrics": [
            {
                "key": "cycle_production_kwh",
                "label": "Produção do ciclo",
                "value": "100.000",
                "unit": "kWh",
                "nature": "MEASURED_AGGREGATE",
                "source": "DAILY_ENERGY_AGGREGATE",
            },
            {
                "key": "bill_energy_component_brl",
                "label": "Componente energético da fatura",
                "value": "45.20",
                "unit": "BRL",
                "nature": "CALCULATED",
                "source": "MPLACAS_DETERMINISTIC_ENGINE",
            },
        ],
        "quality": [],
        "diagnostics": [],
        "priority_actions": [],
        "trend": None,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.mark.asyncio
async def test_legacy_snapshot_without_new_metrics_still_deserializes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Legacy snapshot plant")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="LEGACY-001")
        session.add(device)
        await session.flush()
        bill = UtilityBillRecord(
            plant_id=plant.id,
            distributor="EQUATORIAL_GO",
            reference_month="2026-05",
            cycle_start=date(2026, 5, 31),
            cycle_end=date(2026, 5, 31),
            billed_days=1,
            imported_kwh=Decimal("20"),
            injected_kwh=Decimal("40"),
            compensated_kwh=Decimal("20"),
            credit_balance_kwh=Decimal("50"),
            total_amount_brl=Decimal("60"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="4" * 64,
            reviewed_at=datetime(2026, 5, 31, tzinfo=UTC),
        )
        session.add_all(
            [
                bill,
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 5, 31),
                    energy_kwh=Decimal("100"),
                    status=DataStatus.CONSOLIDATED,
                ),
            ]
        )
        await session.commit()

        legacy_payload_json = _legacy_payload_json(plant_id=plant.id, bill_id=bill.id)
        legacy_sha256 = hashlib.sha256(legacy_payload_json.encode("utf-8")).hexdigest()
        record = MonthlyReportSnapshotRecord(
            plant_id=plant.id,
            bill_id=bill.id,
            reference_month="2026-05",
            schema_version="1.0",
            calculation_version="0.2.0",
            payload_json=legacy_payload_json,
            payload_sha256=legacy_sha256,
        )
        session.add(record)
        await session.commit()

        snapshot = await MonthlyReportSnapshotRepository(session).by_bill_id(
            bill.id,
            plant_id=plant.id,
        )
        assert snapshot is not None
        assert snapshot.report.reference_month == "2026-05"
        keys = [item.key for item in snapshot.report.metrics]
        assert "estimated_savings_brl" not in keys
        assert "savings_unavailable_reason" not in keys

        # O hash gravado nunca é recalculado ou mutado por este código: o
        # payload lido do banco continua batendo byte a byte com o hash
        # persistido, exatamente como antes da Etapa A.
        stored = await session.scalar(
            select(MonthlyReportSnapshotRecord).where(MonthlyReportSnapshotRecord.id == record.id)
        )
        assert stored is not None
        assert stored.payload_sha256 == legacy_sha256
        assert (
            hashlib.sha256(stored.payload_json.encode("utf-8")).hexdigest() == legacy_sha256
        )

    await engine.dispose()
