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


def _bill(
    *,
    plant_id: uuid.UUID,
    reference_month: str,
    source_hash: str,
    generation_cycle_kwh: Decimal | None = None,
) -> UtilityBillRecord:
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
        generation_cycle_kwh=generation_cycle_kwh,
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
    extra_metrics: dict[str, str] | None = None,
    calculation_version: str = "0.2.0",
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
    for key, value in (extra_metrics or {}).items():
        metrics.append(
            {
                "key": key,
                "label": key,
                "value": value,
                "unit": "kWh",
                "nature": "MEASURED",
                "source": "UTILITY_BILL",
            }
        )
    payload = {
        "schema_version": "1.0",
        "calculation_version": calculation_version,
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
    extra_metrics: dict[str, str] | None = None,
    calculation_version: str = "0.2.0",
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
        extra_metrics=extra_metrics,
        calculation_version=calculation_version,
    )
    return MonthlyReportSnapshotRecord(
        plant_id=plant_id,
        bill_id=bill_id,
        reference_month=reference_month,
        schema_version="1.0",
        calculation_version=calculation_version,
        payload_json=payload_json,
        payload_sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
    )


async def _seed_cycles(
    factory,
    *,
    plant_id: uuid.UUID,
    months: list[str],
    generation_cycle_kwh: Decimal | None = None,
    **snapshot_kwargs,
) -> None:
    async with factory() as session:
        for index, month in enumerate(months):
            bill = _bill(
                plant_id=plant_id,
                reference_month=month,
                source_hash=f"{index}" * 64,
                generation_cycle_kwh=generation_cycle_kwh,
            )
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

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01", "2026-02"]))

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A), "limit": 12},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cycles_returned"] == 2
    assert [item["reference_month"] for item in body["cycles"]] == ["2026-01", "2026-02"]


def _history_cycle(token: str) -> dict:
    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 200
    return response.json()["cycles"][0]


_SEPT_METRICS = {
    "injected_kwh": "235",
    "imported_kwh": "221",
    "estimated_self_consumption_kwh": "348.210",
}


def test_cycle_carries_bill_dates_and_meter_injection_side_by_side(cross_tenant_setup) -> None:
    # ADR-083, etapa 3: placas (inversor) × distribuidora no MESMO ciclo da
    # fatura. Datas vêm da fatura confirmada; injeção, importação e autoconsumo
    # vêm do snapshot, tal como gravados (nada recalculado na leitura). Só é
    # "medidor" com snapshot 0.3.0+ E fatura com a leitura do medidor (ADR-078).
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-09"],
            production_kwh="583.210",
            extra_metrics=_SEPT_METRICS,
            calculation_version="0.4.0",
            generation_cycle_kwh=Decimal("235"),
        )
    )

    cycle = _history_cycle(token_a)
    assert cycle["cycle_start"] == "2026-09-28"
    assert cycle["cycle_end"] == "2026-09-28"
    assert cycle["production_kwh"] == "583.210"
    assert cycle["grid_injection_kwh"] == "235"
    assert cycle["grid_injection_basis"] == "METER"
    assert cycle["distributor"] == "EQUATORIAL_GO"
    assert cycle["imported_kwh"] == "221"
    assert cycle["self_consumption_kwh"] == "348.210"


def test_pre_0_3_snapshot_injection_is_bill_line_not_meter(cross_tenant_setup) -> None:
    # Snapshot 0.2.0 é imutável e guardou a linha "INJEÇÃO SCEE" (energia
    # compensada), mesmo que a fatura hoje tenha a leitura do medidor.
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-09"],
            extra_metrics=_SEPT_METRICS,
            calculation_version="0.2.0",
            generation_cycle_kwh=Decimal("235"),
        )
    )

    cycle = _history_cycle(token_a)
    assert cycle["grid_injection_kwh"] == "235"
    assert cycle["grid_injection_basis"] == "BILL_LINE"


def test_meter_reading_completed_after_snapshot_is_not_meter(cross_tenant_setup) -> None:
    # A fatura ganhou a leitura do medidor pelo PDF DEPOIS do snapshot 0.4.0
    # (ADR-081): o snapshot ainda guarda a linha da fatura (221), não o
    # medidor (235). Só a igualdade prova que veio do medidor.
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-09"],
            extra_metrics={**_SEPT_METRICS, "injected_kwh": "221"},
            calculation_version="0.4.0",
            generation_cycle_kwh=Decimal("235"),
        )
    )

    assert _history_cycle(token_a)["grid_injection_basis"] == "BILL_LINE"


def test_bill_without_meter_reading_injection_is_bill_line(cross_tenant_setup) -> None:
    # Em 0.3.0+, `reconcile_bill` cai na linha da fatura quando ela não traz
    # `generation_cycle_kwh`: também não é medidor.
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-09"],
            extra_metrics=_SEPT_METRICS,
            calculation_version="0.4.0",
            generation_cycle_kwh=None,
        )
    )

    assert _history_cycle(token_a)["grid_injection_basis"] == "BILL_LINE"


def test_old_snapshot_without_meter_metrics_returns_null_not_zero(cross_tenant_setup) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01"]))

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )

    cycle = response.json()["cycles"][0]
    assert cycle["grid_injection_kwh"] is None
    assert cycle["grid_injection_basis"] is None
    assert cycle["imported_kwh"] is None
    assert cycle["self_consumption_kwh"] is None
    assert cycle["cycle_start"] == "2026-01-28"


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


def test_load_recent_monthly_reports_feeds_pdf_history_within_scope(
    cross_tenant_setup,
) -> None:
    """Histórico do PDF: só snapshots já gravados, limitados e dentro do escopo."""
    from mplacas.core.authorization import PlantScope
    from mplacas.reports.export.pdf_renderer import build_monthly_report_pdf
    from mplacas.reports.history_service import load_recent_monthly_reports

    factory, _, _, _, _ = cross_tenant_setup
    import asyncio
    import io

    from pypdf import PdfReader

    months = [f"2026-{month:02d}" for month in range(1, 4)]
    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=months))

    async def _run():
        async with factory() as session:
            before = await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))
            reports = await load_recent_monthly_reports(session, plant_id=PLANT_A, limit=2)
            outside = await load_recent_monthly_reports(
                session,
                plant_id=PLANT_A,
                plant_scope=PlantScope.restricted({uuid.uuid4()}),
            )
            after = await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))
            return reports, outside, before, after

    reports, outside, before, after = asyncio.run(_run())

    assert [report.reference_month for report in reports] == ["2026-02", "2026-03"]
    assert outside == ()
    assert before == after == 3  # leitura estrita: nada materializado

    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(
            io.BytesIO(build_monthly_report_pdf(reports[-1], history=reports))
        ).pages
    )
    assert "Março/2026" in text and "Fevereiro/2026" in text
    assert "Janeiro/2026" not in text  # fora do limite pedido


def _pdf_text(content: bytes) -> str:
    import io

    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)


def test_latest_pdf_route_includes_history_within_tenant(cross_tenant_setup) -> None:
    factory, _, _, token_a, token_b = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01", "2026-02", "2026-03"]))
    client = TestClient(app)

    response = client.get(
        "/reports/monthly/latest.pdf",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "HISTÓRICO DOS ÚLTIMOS CICLOS" in text
    for month in ("Janeiro/2026", "Fevereiro/2026", "Março/2026"):
        assert month in text

    # Outra organização não baixa o PDF (nem o histórico) desta usina.
    foreign = client.get(
        "/reports/monthly/latest.pdf",
        headers=_headers(token_b),
        params={"plant_id": str(PLANT_A)},
    )
    assert foreign.status_code in (403, 404)


def test_corrupted_old_snapshot_drops_history_but_not_the_current_pdf(
    cross_tenant_setup,
) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-01", "2026-02", "2026-03"]))

    async def _corrupt_january() -> None:
        async with factory() as session:
            record = await session.scalar(
                select(MonthlyReportSnapshotRecord).where(
                    MonthlyReportSnapshotRecord.reference_month == "2026-01"
                )
            )
            assert record is not None
            record.payload_sha256 = "0" * 64
            await session.commit()

    asyncio.run(_corrupt_january())

    response = TestClient(app).get(
        "/reports/monthly/latest.pdf",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Março/2026" in text  # ciclo atual continua saindo
    assert "HISTÓRICO DOS ÚLTIMOS CICLOS" not in text


def test_single_cycle_pdf_has_no_history_section(cross_tenant_setup) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-03"]))

    response = TestClient(app).get(
        "/reports/monthly/latest.pdf",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 200
    assert "HISTÓRICO" not in _pdf_text(response.content)


def test_export_drain_pdf_includes_history(cross_tenant_setup, monkeypatch) -> None:
    import asyncio

    import mplacas.reports.drain as drain
    from mplacas.reports.db_models import ReportExportTask

    factory, _, _, _, _ = cross_tenant_setup
    monkeypatch.setattr(drain, "SessionFactory", factory)
    asyncio.run(_seed_cycles(factory, plant_id=PLANT_A, months=["2026-02", "2026-03"]))

    async def _enqueue() -> uuid.UUID:
        async with factory() as session:
            task = ReportExportTask(
                plant_id=PLANT_A, reference_month="2026-03", format="pdf", status="pending"
            )
            session.add(task)
            await session.commit()
            return task.id

    task_id = asyncio.run(_enqueue())
    result = asyncio.run(drain.drain_report_exports())
    assert (result.completed, result.failed) == (1, 0)

    async def _artifact() -> bytes:
        async with factory() as session:
            task = await session.get(ReportExportTask, task_id)
            assert task is not None and task.status == "completed"
            assert task.artifact_bytes is not None
            return task.artifact_bytes

    text = _pdf_text(asyncio.run(_artifact()))
    assert "HISTÓRICO DOS ÚLTIMOS CICLOS" in text
    assert "Fevereiro/2026" in text


def test_cycle_carries_utility_check_with_credit_conservation(cross_tenant_setup) -> None:
    # ADR-084: a conferência usa a fatura do mês anterior como saldo de partida.
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-08", "2026-09"],
            extra_metrics=_SEPT_METRICS,
            calculation_version="0.4.0",
            generation_cycle_kwh=Decimal("30"),
        )
    )

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )
    first, second = response.json()["cycles"]
    # Sem fatura anterior: não dá para conferir, nunca "OK" por omissão.
    assert first["utility_check"]["verdict"] == "UNVERIFIABLE"
    assert "NO_PREVIOUS_BILL" in first["utility_check"]["reasons"]
    # Fixture: 30 do medidor + 50 de saldo − 20 usados ≠ 50 de saldo → 10 kWh sumidos.
    assert second["utility_check"]["verdict"] == "LOSS"
    assert second["utility_check"]["missing_credits_kwh"] == "10.00"


def test_estimated_production_cycle_skips_physical_checks(cross_tenant_setup) -> None:
    # ADR-084/082: dia estimado pelo sol pode ter elevado a produção até o
    # medidor — o ciclo não roda impossível/suspeita nem entra na referência.
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-08", "2026-09"],
            production_kwh="10.000",
            quality={
                "missing_days": "0",
                "provisional_days": "0",
                "incomplete_days": "0",
                "unavailable_days": "0",
                "estimated_production_days": "2",
            },
            calculation_version="0.4.0",
            generation_cycle_kwh=Decimal("30"),
        )
    )

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )
    second = response.json()["cycles"][1]["utility_check"]
    # 30 do medidor > 10 produzidos, mas a produção é estimada: não acusa.
    assert second["verdict"] != "IMPOSSIBLE"
    assert "PRODUCTION_ESTIMATED" in second["reasons"]
    assert second["export_share_percent"] is None


def test_ambiguous_previous_month_bills_skip_credit_check(cross_tenant_setup) -> None:
    factory, _, _, token_a, _ = cross_tenant_setup
    import asyncio

    async def _seed() -> None:
        async with factory() as session:
            refaturada = _bill(
                plant_id=PLANT_A,
                reference_month="2026-08",
                source_hash="r" * 64,
                generation_cycle_kwh=Decimal("30"),
            )
            refaturada.cycle_start = date(2026, 8, 1)
            refaturada.credit_balance_kwh = Decimal("12")
            session.add(refaturada)
            await session.commit()

    asyncio.run(
        _seed_cycles(
            factory,
            plant_id=PLANT_A,
            months=["2026-08", "2026-09"],
            calculation_version="0.4.0",
            generation_cycle_kwh=Decimal("30"),
        )
    )
    asyncio.run(_seed())

    response = TestClient(app).get(
        "/reports/monthly/history",
        headers=_headers(token_a),
        params={"plant_id": str(PLANT_A)},
    )
    september = [c for c in response.json()["cycles"] if c["reference_month"] == "2026-09"][0]
    assert september["utility_check"]["verdict"] == "UNVERIFIABLE"
    assert "AMBIGUOUS_PREVIOUS_BILL" in september["utility_check"]["reasons"]
