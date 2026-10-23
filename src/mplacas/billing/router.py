from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from mplacas.audit.repository import AuditEventRepository
from mplacas.billing.completion import BillCompletionConflict, complete_missing_fields
from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.config import get_settings
from mplacas.core.tenancy import AdminPlant, AdminPrincipal, resolve_admin_plant_scope
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.reports.snapshot import materialize_monthly_report_snapshot
from mplacas.telegram.pdf import PdfTextExtractionError, extract_pdf_text_isolated

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
)


class BillTextIntake(BaseModel):
    plant_id: uuid.UUID | None = None
    text: str = Field(min_length=20)


def _optional_decimal(value: object) -> str | None:
    return None if value is None else str(value)


def _serialize(record) -> dict[str, object]:
    return {
        "id": str(record.id),
        "plant_id": str(record.plant_id),
        "distributor": record.distributor,
        "reference_month": record.reference_month,
        "cycle_start": record.cycle_start,
        "cycle_end": record.cycle_end,
        "billed_days": record.billed_days,
        "imported_kwh": str(record.imported_kwh),
        "injected_kwh": str(record.injected_kwh),
        "compensated_kwh": str(record.compensated_kwh),
        "credit_balance_kwh": str(record.credit_balance_kwh),
        "total_amount_brl": str(record.total_amount_brl),
        "public_lighting_brl": str(record.public_lighting_brl),
        # Campos opcionais que a fatura SCEE pode trazer (ADR-050/ADR-056).
        # Expostos para a conferência humana antes de confirmar: sem eles a
        # tela não consegue mostrar ao dono da usina tudo o que foi lido.
        "generation_cycle_kwh": _optional_decimal(record.generation_cycle_kwh),
        "tariff_with_taxes_brl_kwh": _optional_decimal(record.tariff_with_taxes_brl_kwh),
        "tariff_without_taxes_brl_kwh": _optional_decimal(record.tariff_without_taxes_brl_kwh),
        "wire_b_tariff_brl_kwh": _optional_decimal(record.wire_b_tariff_brl_kwh),
        "status": record.status.value,
        "created_at": record.created_at,
        "reviewed_at": record.reviewed_at,
    }


@router.post("/intake-text", status_code=status.HTTP_202_ACCEPTED)
async def intake_bill_text(
    request: Request, payload: BillTextIntake, principal: AdminPrincipal
) -> dict[str, object]:
    # plant_id is carried in the request body (not a query param), so it
    # cannot be resolved via the AdminPlant dependency directly — reuse the
    # same organization-scoped resolve+validate logic explicitly instead.
    # Resolved before parsing the (untrusted) bill text so a cross-tenant
    # request is rejected without ever processing its payload.
    scoped = await resolve_admin_plant_scope(principal, payload.plant_id)
    plant_id = scoped.plant_id

    settings = get_settings()
    if len(payload.text.encode("utf-8")) > settings.bill_text_max_bytes:
        raise HTTPException(status_code=413, detail="bill text exceeds configured size limit")
    try:
        bill = parse_equatorial_bill_text(payload.text)
    except BillParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        repository = UtilityBillRepository(session)
        try:
            record = await repository.create_pending(
                bill,
                plant_id=plant_id,
                source_text=payload.text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await AuditEventRepository(session).record(
            request,
            action="billing.intake_text",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
                "status": record.status.value,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {"status": "pending_review", "bill": _serialize(record)}


_PDF_CONTENT_TYPES = frozenset({"application/pdf", "application/octet-stream"})


async def _read_limited_body(request: Request, *, max_bytes: int) -> bytes:
    """Lê o corpo da requisição parando assim que passar do limite.

    Não confia no ``Content-Length`` (pode faltar ou mentir): conta os bytes
    que realmente chegam e aborta com 413 antes de acumular o excesso.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status_code=413, detail="O PDF passa do tamanho máximo permitido.")
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > max_bytes:
            raise HTTPException(status_code=413, detail="O PDF passa do tamanho máximo permitido.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/intake-pdf", status_code=status.HTTP_202_ACCEPTED)
async def intake_bill_pdf(
    request: Request,
    response: Response,
    scoped: AdminPlant,
) -> dict[str, object]:
    """Importa a fatura em PDF enviada pelo site (mesmo leitor do Telegram).

    O corpo é o PDF cru (``Content-Type: application/pdf``), sem multipart —
    evita uma dependência nova só para um arquivo. A usina vem do
    ``plant_id`` na query e é validada por ``AdminPlant`` ANTES de qualquer
    byte do documento ser lido, como em ``/intake-text``. O PDF nunca é
    gravado: só o texto extraído vira ``source_text`` da fatura pendente,
    igual ao fluxo do Telegram, e a extração roda em processo isolado com
    tempo, CPU e memória limitados (``extract_pdf_text_isolated``).
    """
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in _PDF_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Envie a fatura em PDF.")

    settings = get_settings()
    # Os limites `telegram_*` valem para qualquer PDF de fatura, não só para o
    # que chega pelo bot: é o mesmo documento, com o mesmo risco.
    content = await _read_limited_body(request, max_bytes=settings.telegram_document_max_bytes)
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="O arquivo enviado não é um PDF.")

    try:
        source_text = await extract_pdf_text_isolated(
            content,
            max_pages=settings.telegram_pdf_max_pages,
            max_text_bytes=settings.bill_text_max_bytes,
            timeout_seconds=settings.telegram_pdf_parse_timeout_seconds,
            cpu_seconds=settings.telegram_pdf_parse_cpu_seconds,
            memory_bytes=settings.telegram_pdf_parse_memory_bytes,
        )
    except PdfTextExtractionError as exc:
        # A mensagem da biblioteca nunca chega ao cliente (pode conter trechos
        # do documento) — só um texto fixo.
        raise HTTPException(
            status_code=422,
            detail=(
                "Não foi possível ler o texto deste PDF. "
                "Envie a fatura original da distribuidora, sem senha."
            ),
        ) from exc
    try:
        bill = parse_equatorial_bill_text(source_text)
    except BillParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "O PDF foi lido, mas não parece uma fatura da Equatorial Goiás "
                "com os campos esperados."
            ),
        ) from exc

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        repository = UtilityBillRepository(session)
        # Reenvio do mesmo PDF (mesmo texto extraído) não cria nada: devolve o
        # registro existente com o estado REAL dele (pendente, confirmada ou
        # rejeitada), HTTP 200 em vez de 202, e a auditoria marca o reenvio —
        # para nenhum cliente nem a trilha registrarem uma importação que não
        # aconteceu.
        existing = await repository.find_by_source_text(
            plant_id=scoped.plant_id, source_text=source_text
        )
        confirmed = (
            None
            if existing is not None
            else await repository.find_confirmed_for_month(
                plant_id=scoped.plant_id,
                distributor=bill.distributor,
                reference_month=bill.reference_month,
            )
        )
        if confirmed is not None:
            # Mês já confirmado: o PDF só pode completar campos vazios da MESMA
            # fatura (ex.: tarifa que o texto do Telegram não trazia). Nunca
            # cria outra fatura do mês nem reescreve o que foi conferido.
            try:
                filled = complete_missing_fields(confirmed, bill)
            except BillCompletionConflict as exc:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Já existe uma fatura confirmada deste mês com valores "
                        "diferentes dos lidos neste PDF. Nada foi alterado."
                    ),
                ) from exc
            await AuditEventRepository(session).record(
                request,
                action="billing.complete_from_pdf",
                resource_type="utility_bill",
                resource_id=str(confirmed.id),
                outcome="SUCCEEDED",
                details={
                    "plant_id": str(confirmed.plant_id),
                    "reference_month": confirmed.reference_month,
                    "filled_fields": list(filled),
                },
            )
            await session.commit()
            await session.refresh(confirmed)
            response.status_code = status.HTTP_200_OK
            return {
                "status": "completed_missing_fields" if filled else "already_imported",
                "filled_fields": list(filled),
                "bill": _serialize(confirmed),
            }
        if existing is not None:
            record = existing
        else:
            try:
                record = await repository.create_pending(
                    bill,
                    plant_id=scoped.plant_id,
                    source_text=source_text,
                )
            except ValueError as exc:
                # Mensagem fixa: o `ValueError` de `bill.validate()` pode trazer
                # valores lidos do documento.
                raise HTTPException(
                    status_code=409,
                    detail="Os valores lidos desta fatura não passaram na validação.",
                ) from exc
        duplicate = existing is not None
        await AuditEventRepository(session).record(
            request,
            action="billing.intake_pdf",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
                "status": record.status.value,
                "duplicate": duplicate,
            },
        )
        await session.commit()
        await session.refresh(record)
    if duplicate:
        response.status_code = status.HTTP_200_OK
        return {"status": "already_imported", "bill": _serialize(record)}
    return {"status": "pending_review", "bill": _serialize(record)}


@router.get("/pending")
async def pending_bills(
    scoped: AdminPlant,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        records = await UtilityBillRepository(session).list_pending(
            limit=limit,
            plant_id=scoped.plant_id,
        )
    return {"count": len(records), "items": [_serialize(record) for record in records]}


@router.post("/{bill_id}/confirm")
async def confirm_bill(
    request: Request,
    bill_id: uuid.UUID,
    principal: AdminPrincipal,
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        repository = UtilityBillRepository(session)
        record = await repository.get_by_id(bill_id)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found for plant")
        # The plant is already on the bill row (ADR-069 § E.2 opção 5) — no
        # plant_id is inferred or accepted from the caller, so a caller with
        # a restricted PlantScope (or a different organization entirely)
        # cannot confirm a bill outside its own scope. 404, not 403: same
        # "do not reveal cross-tenant existence" convention used by
        # resolve_read_plant / resolve_admin_plant_scope.
        principal.require_plant_access(record.plant_id)
        try:
            await repository.confirm(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        report_snapshot = await materialize_monthly_report_snapshot(
            session,
            bill_id=record.id,
            plant_id=record.plant_id,
        )
        await AuditEventRepository(session).record(
            request,
            action="billing.confirm",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
                "report_snapshot_id": str(report_snapshot.id),
                "report_snapshot_sha256": report_snapshot.payload_sha256,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {
        "status": "confirmed",
        "bill": _serialize(record),
        "report_snapshot": {
            "id": str(report_snapshot.id),
            "sha256": report_snapshot.payload_sha256,
            "schema_version": report_snapshot.report.schema_version,
            "calculation_version": report_snapshot.report.calculation_version,
        },
    }


@router.post("/{bill_id}/reject")
async def reject_bill(
    request: Request,
    bill_id: uuid.UUID,
    principal: AdminPrincipal,
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        repository = UtilityBillRepository(session)
        record = await repository.get_by_id(bill_id)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found for plant")
        # Same "derive plant from the record" rationale as confirm_bill above.
        principal.require_plant_access(record.plant_id)
        try:
            await repository.reject(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await AuditEventRepository(session).record(
            request,
            action="billing.reject",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {"status": "rejected", "bill": _serialize(record)}
