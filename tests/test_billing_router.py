from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.billing.db_models import BillStatus
from mplacas.billing.models import UtilityBill
from mplacas.core.config import get_settings
from mplacas.main import app
import mplacas.billing.router as billing_router


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, model, identity):
        return SimpleNamespace(id=identity)

    async def commit(self) -> None:
        return None

    async def refresh(self, record) -> None:
        return None


class FakeAuditEventRepository:
    events: list[dict[str, object]] = []

    def __init__(self, session) -> None:
        self.session = session

    async def record(self, request, **kwargs):
        self.events.append(kwargs)
        return SimpleNamespace()


class FakeUtilityBillRepository:
    def __init__(self, session) -> None:
        self.session = session

    async def create_pending(self, bill, *, plant_id, source_text):
        return SimpleNamespace(
            id=uuid.UUID("00000000-0000-0000-0000-000000000132"),
            plant_id=plant_id,
            distributor=bill.distributor,
            reference_month=bill.reference_month,
            cycle_start=bill.cycle_start,
            cycle_end=bill.cycle_end,
            billed_days=bill.billed_days,
            imported_kwh=bill.imported_kwh,
            injected_kwh=bill.injected_kwh,
            compensated_kwh=bill.compensated_kwh,
            credit_balance_kwh=bill.credit_balance_kwh,
            total_amount_brl=bill.total_amount_brl,
            public_lighting_brl=bill.public_lighting_brl,
            status=BillStatus.PENDING_REVIEW,
            created_at=None,
            reviewed_at=None,
        )


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    get_settings.cache_clear()


def test_billing_intake_text_records_sanitized_audit_event(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000032")
    raw_text = "private customer bill text with enough bytes"

    def fake_parse(text: str) -> UtilityBill:
        assert text == raw_text
        return UtilityBill(
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
        )

    monkeypatch.setattr(billing_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(billing_router, "parse_equatorial_bill_text", fake_parse)
    monkeypatch.setattr(billing_router, "UtilityBillRepository", FakeUtilityBillRepository)
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(billing_router, "AuditEventRepository", FakeAuditEventRepository)

    response = TestClient(app).post(
        "/billing/intake-text",
        headers={"X-API-Key": "synthetic-key"},
        json={"plant_id": str(plant_id), "text": raw_text},
    )

    assert response.status_code == 202
    assert raw_text not in response.text
    event = FakeAuditEventRepository.events[-1]
    assert event["action"] == "billing.intake_text"
    assert event["resource_type"] == "utility_bill"
    assert event["resource_id"] == "00000000-0000-0000-0000-000000000132"
    assert event["outcome"] == "SUCCEEDED"
    assert event["details"] == {
        "plant_id": str(plant_id),
        "reference_month": "2026-06",
        "status": "PENDING_REVIEW",
    }
    get_settings.cache_clear()


def test_billing_confirmation_materializes_snapshot_before_commit(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000032")
    bill_id = uuid.UUID("00000000-0000-0000-0000-000000000132")
    snapshot_id = uuid.UUID("00000000-0000-0000-0000-000000000134")
    record = SimpleNamespace(
        id=bill_id,
        plant_id=plant_id,
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
        created_at=None,
        reviewed_at=None,
    )

    class FakeConfirmRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get(self, record_id, *, plant_id):
            assert record_id == bill_id
            assert plant_id == record.plant_id
            return record

        async def confirm(self, target):
            target.status = BillStatus.CONFIRMED
            return target

    async def fake_materialize(session, *, bill_id, plant_id):
        assert bill_id == record.id
        assert plant_id == record.plant_id
        assert record.status is BillStatus.CONFIRMED
        return SimpleNamespace(
            id=snapshot_id,
            payload_sha256="c" * 64,
            report=SimpleNamespace(schema_version="1.0", calculation_version="0.2.0"),
        )

    monkeypatch.setattr(billing_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(billing_router, "UtilityBillRepository", FakeConfirmRepository)
    monkeypatch.setattr(
        billing_router,
        "materialize_monthly_report_snapshot",
        fake_materialize,
    )
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(billing_router, "AuditEventRepository", FakeAuditEventRepository)

    response = TestClient(app).post(
        f"/billing/{bill_id}/confirm",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id)},
    )

    assert response.status_code == 200
    assert response.json()["report_snapshot"] == {
        "id": str(snapshot_id),
        "sha256": "c" * 64,
        "schema_version": "1.0",
        "calculation_version": "0.2.0",
    }
    details = FakeAuditEventRepository.events[-1]["details"]
    assert details["report_snapshot_id"] == str(snapshot_id)
    assert details["report_snapshot_sha256"] == "c" * 64
    get_settings.cache_clear()
