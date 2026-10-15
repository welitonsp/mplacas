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
            generation_cycle_kwh=bill.generation_cycle_kwh,
            tariff_with_taxes_brl_kwh=bill.tariff_with_taxes_brl_kwh,
            tariff_without_taxes_brl_kwh=bill.tariff_without_taxes_brl_kwh,
            wire_b_tariff_brl_kwh=bill.wire_b_tariff_brl_kwh,
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
        generation_cycle_kwh=None,
        tariff_with_taxes_brl_kwh=None,
        tariff_without_taxes_brl_kwh=None,
        wire_b_tariff_brl_kwh=None,
        status=BillStatus.PENDING_REVIEW,
        created_at=None,
        reviewed_at=None,
    )

    class FakeConfirmRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_by_id(self, record_id):
            assert record_id == bill_id
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


# --- POST /billing/intake-pdf -------------------------------------------------

_PDF_BYTES = b"%PDF-1.7\n synthetic bill bytes"
_PDF_PLANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000032")


def _synthetic_bill() -> UtilityBill:
    return UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-09",
        cycle_start=date(2026, 8, 17),
        cycle_end=date(2026, 9, 14),
        billed_days=29,
        imported_kwh=Decimal("221.00"),
        injected_kwh=Decimal("221.00"),
        compensated_kwh=Decimal("221.00"),
        credit_balance_kwh=Decimal("17.98"),
        total_amount_brl=Decimal("70.22"),
        public_lighting_brl=Decimal("30.21"),
        generation_cycle_kwh=Decimal("235.00"),
        tariff_with_taxes_brl_kwh=Decimal("0.787589"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
    )


def _install_pdf_fakes(monkeypatch, *, extracted_text: str = "texto extraido da fatura sintetica"):
    calls: dict[str, object] = {}

    async def fake_extract(content: bytes, **kwargs) -> str:
        calls["content"] = content
        calls["kwargs"] = kwargs
        return extracted_text

    def fake_parse(text: str) -> UtilityBill:
        calls["parsed_text"] = text
        return _synthetic_bill()

    monkeypatch.setattr(billing_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(billing_router, "extract_pdf_text_isolated", fake_extract)
    monkeypatch.setattr(billing_router, "parse_equatorial_bill_text", fake_parse)
    monkeypatch.setattr(billing_router, "UtilityBillRepository", FakeUtilityBillRepository)
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(billing_router, "AuditEventRepository", FakeAuditEventRepository)
    return calls


def _post_pdf(body: bytes, *, content_type: str = "application/pdf"):
    return TestClient(app).post(
        f"/billing/intake-pdf?plant_id={_PDF_PLANT_ID}",
        headers={"X-API-Key": "synthetic-key", "Content-Type": content_type},
        content=body,
    )


def test_intake_pdf_creates_pending_bill_with_all_read_fields(monkeypatch) -> None:
    _configure(monkeypatch)
    calls = _install_pdf_fakes(monkeypatch)

    response = _post_pdf(_PDF_BYTES)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending_review"
    bill = body["bill"]
    assert bill["reference_month"] == "2026-09"
    assert bill["total_amount_brl"] == "70.22"
    # Campos opcionais da fatura SCEE chegam para a conferência humana.
    assert bill["generation_cycle_kwh"] == "235.00"
    assert bill["tariff_with_taxes_brl_kwh"] == "0.787589"
    assert bill["tariff_without_taxes_brl_kwh"] == "0.613030"
    assert bill["wire_b_tariff_brl_kwh"] == "0.175126"
    # Mesmo leitor e mesmos limites do Telegram; o texto extraído é o que vai
    # para o parser.
    assert calls["content"] == _PDF_BYTES
    settings = get_settings()
    assert calls["kwargs"]["max_pages"] == settings.telegram_pdf_max_pages
    assert calls["kwargs"]["max_text_bytes"] == settings.bill_text_max_bytes
    assert calls["parsed_text"] == "texto extraido da fatura sintetica"
    # O texto da fatura nunca vai para a resposta nem para a auditoria.
    assert "texto extraido" not in response.text
    event = FakeAuditEventRepository.events[-1]
    assert event["action"] == "billing.intake_pdf"
    assert event["details"] == {
        "plant_id": str(_PDF_PLANT_ID),
        "reference_month": "2026-09",
        "status": "PENDING_REVIEW",
    }
    get_settings.cache_clear()


def test_intake_pdf_rejects_non_pdf_content_type(monkeypatch) -> None:
    _configure(monkeypatch)
    calls = _install_pdf_fakes(monkeypatch)

    response = _post_pdf(_PDF_BYTES, content_type="image/png")

    assert response.status_code == 415
    assert "content" not in calls
    get_settings.cache_clear()


def test_intake_pdf_rejects_bytes_that_are_not_a_pdf(monkeypatch) -> None:
    _configure(monkeypatch)
    calls = _install_pdf_fakes(monkeypatch)

    response = _post_pdf(b"<html>not a pdf</html>")

    assert response.status_code == 415
    assert response.json() == {"detail": "O arquivo enviado não é um PDF."}
    assert "content" not in calls
    get_settings.cache_clear()


def test_intake_pdf_rejects_body_over_size_limit(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("MPLACAS_TELEGRAM_DOCUMENT_MAX_BYTES", "16")
    get_settings.cache_clear()
    calls = _install_pdf_fakes(monkeypatch)

    response = _post_pdf(_PDF_BYTES)

    assert response.status_code == 413
    assert "content" not in calls
    get_settings.cache_clear()


def test_intake_pdf_extraction_failure_returns_fixed_message(monkeypatch) -> None:
    _configure(monkeypatch)
    _install_pdf_fakes(monkeypatch)

    async def failing_extract(content: bytes, **kwargs) -> str:
        raise billing_router.PdfTextExtractionError("segredo do documento: CPF 000.000.000-00")

    monkeypatch.setattr(billing_router, "extract_pdf_text_isolated", failing_extract)

    response = _post_pdf(_PDF_BYTES)

    assert response.status_code == 422
    assert "segredo" not in response.text
    assert "CPF" not in response.text
    get_settings.cache_clear()


def test_intake_pdf_parse_failure_returns_422_without_document_text(monkeypatch) -> None:
    _configure(monkeypatch)
    _install_pdf_fakes(monkeypatch, extracted_text="texto qualquer sem campos de fatura")

    def failing_parse(text: str) -> UtilityBill:
        raise billing_router.BillParseError("missing reference_month in: texto qualquer")

    monkeypatch.setattr(billing_router, "parse_equatorial_bill_text", failing_parse)

    response = _post_pdf(_PDF_BYTES)

    assert response.status_code == 422
    assert "texto qualquer" not in response.text
    get_settings.cache_clear()


def test_intake_pdf_requires_credentials(monkeypatch) -> None:
    _configure(monkeypatch)
    calls = _install_pdf_fakes(monkeypatch)

    response = TestClient(app).post(
        f"/billing/intake-pdf?plant_id={_PDF_PLANT_ID}",
        headers={"Content-Type": "application/pdf"},
        content=_PDF_BYTES,
    )

    assert response.status_code in (401, 403)
    assert "content" not in calls
    get_settings.cache_clear()
