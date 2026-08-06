from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.config import get_settings
from mplacas.core.tenancy import _infer_single_plant_for_organization_in_session
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context, set_tenant_context
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.telegram.client import TelegramClient, TelegramClientError
from mplacas.telegram.document_processing import (
    TelegramDocumentProcessingError,
    process_pdf_bill,
)
from mplacas.telegram.pdf import PdfTextExtractionError, extract_pdf_text_isolated
from mplacas.telegram.service import (
    TelegramUpdateError,
    extract_chat_id,
    parse_authorized_update,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _pending_message(reference_month: str, plant_name: str) -> str:
    return (
        f"Fatura {reference_month} recebida e analisada, lançada na usina {plant_name}.\n"
        "Ela ficou pendente de revisão humana antes da consolidação.\n"
        "Usina errada? Use /usina <nome> e reenvie."
    )


_COMMAND_HELP_MESSAGE = (
    "Comando não reconhecido. Use /usinas para listar as usinas da sua conta "
    "ou /usina <nome> para trocar a usina ativa."
)


async def _fetch_plant_name(session: AsyncSession, plant_id: uuid.UUID) -> str:
    """Fetch a plant's ``name`` for use in human-facing messages.

    Falls back to a generic label rather than raising if the row somehow
    vanished between resolution and this lookup — the bill was already
    written against ``plant_id``, so the confirmation message must not fail.
    """
    name = (
        await session.execute(select(Plant.name).where(Plant.id == plant_id))
    ).scalar_one_or_none()
    return name or "usina"


async def _list_plants_for_organization(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[tuple[uuid.UUID, str]]:
    result = await session.execute(
        select(Plant.id, Plant.name)
        .where(Plant.organization_id == organization_id)
        .order_by(Plant.name, Plant.id)
    )
    return [(row[0], row[1]) for row in result]


async def _current_default_plant_id(
    session: AsyncSession, organization_id: uuid.UUID
) -> uuid.UUID | None:
    return (
        await session.execute(
            select(OrganizationRecord.default_plant_id).where(
                OrganizationRecord.id == organization_id
            )
        )
    ).scalar_one_or_none()


def _format_plant_list_message(
    plants: list[tuple[uuid.UUID, str]], default_plant_id: uuid.UUID | None
) -> str:
    if not plants:
        return "Sua conta ainda não tem nenhuma usina cadastrada."
    lines = ["Usinas da sua conta:"]
    for plant_id, name in plants:
        suffix = " (padrão)" if plant_id == default_plant_id else ""
        lines.append(f"- {name}{suffix}")
    lines.append(f"Para trocar: /usina {plants[-1][1]}")
    return "\n".join(lines)


async def _resolve_plant_by_name(
    session: AsyncSession, organization_id: uuid.UUID, name: str
) -> list[tuple[uuid.UUID, str]]:
    """Resolve ``name`` against the organization's plants.

    Case-insensitive exact match takes precedence over a case-insensitive
    prefix match (``ILIKE`` anchored at the start). Always scoped by
    ``organization_id`` in the ``WHERE`` clause, on top of RLS. Returns the
    exact match alone when exactly one exists; otherwise returns every
    prefix candidate (zero, one, or many), leaving ambiguity/absence
    handling to the caller.
    """
    clean_name = name.strip()

    exact_result = await session.execute(
        select(Plant.id, Plant.name).where(
            Plant.organization_id == organization_id,
            func.lower(Plant.name) == clean_name.lower(),
        )
    )
    exact = [(row[0], row[1]) for row in exact_result]
    if len(exact) == 1:
        return exact

    escaped = clean_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    prefix_result = await session.execute(
        select(Plant.id, Plant.name)
        .where(
            Plant.organization_id == organization_id,
            Plant.name.ilike(f"{escaped}%", escape="\\"),
        )
        .order_by(Plant.name, Plant.id)
    )
    return [(row[0], row[1]) for row in prefix_result]


async def _switch_default_plant(
    session: AsyncSession, organization_id: uuid.UUID, name: str
) -> str:
    candidates = await _resolve_plant_by_name(session, organization_id, name)
    if not candidates:
        return "Não encontrei essa usina. Use /usinas para ver a lista."
    if len(candidates) > 1:
        names = ", ".join(candidate_name for _, candidate_name in candidates)
        return (
            "Encontrei mais de uma usina com esse nome: "
            f"{names}. Use /usina <nome completo> para escolher."
        )
    plant_id, plant_name = candidates[0]
    organization = await session.get(OrganizationRecord, organization_id)
    if organization is not None:
        organization.default_plant_id = plant_id
        await session.flush()
    return f"Usina ativa agora: {plant_name}. As próximas faturas serão lançadas nela."


async def _handle_telegram_command(
    session: AsyncSession, organization_id: uuid.UUID, command_text: str
) -> str:
    """Dispatch a Telegram command (``/usinas``, ``/usina <nome>``, ...).

    Unknown commands return help text rather than raising — the webhook
    keeps responding 202 regardless of whether the command was recognized
    (see ADR-069 § E.5).
    """
    parts = command_text.strip().split(maxsplit=1)
    command = parts[0].lower() if parts else ""
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/usinas", "/usina") and not argument:
        plants = await _list_plants_for_organization(session, organization_id)
        default_plant_id = await _current_default_plant_id(session, organization_id)
        return _format_plant_list_message(plants, default_plant_id)

    if command == "/usina":
        return await _switch_default_plant(session, organization_id, argument)

    return _COMMAND_HELP_MESSAGE


async def _resolve_telegram_organization(
    session: AsyncSession, chat_id: int
) -> uuid.UUID:
    """Resolve the organization that owns a given Telegram ``chat_id``.

    Each organization links exactly one Telegram chat via
    ``OrganizationRecord.telegram_chat_id`` (see ADR/PR-6 of the
    multi-tenancy plan). Messages from an unrecognized chat are rejected
    outright — there is no global fallback plant/organization anymore.
    """
    organization_id = (
        await session.execute(
            select(OrganizationRecord.id).where(
                OrganizationRecord.telegram_chat_id == chat_id
            )
        )
    ).scalar_one_or_none()
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram chat is not linked to any organization",
        )
    return organization_id


async def _resolve_telegram_allowed_user_id(
    session: AsyncSession, organization_id: uuid.UUID
) -> int | None:
    """Fetch the organization's own ``telegram_allowed_user_id``.

    Returns ``None`` if the organization hasn't configured one yet — the
    caller must fail closed in that case (see ``telegram_webhook``'s
    docstring/comment on why the process-wide
    ``MPLACAS_TELEGRAM_ALLOWED_USER_ID`` setting is never used as a runtime
    fallback here).
    """
    return (
        await session.execute(
            select(OrganizationRecord.telegram_allowed_user_id).where(
                OrganizationRecord.id == organization_id
            )
        )
    ).scalar_one_or_none()


async def _resolve_telegram_plant_scope(
    session: AsyncSession, organization_id: uuid.UUID
) -> uuid.UUID:
    """Infer the single plant belonging to ``organization_id``.

    Reuses ``core.tenancy``'s organization-scoped plant inference (same 409
    semantics as ``resolve_admin_plant`` when the organization has zero or
    more than one plant), against the same ``session`` already opened for
    organization resolution — avoids a second connection/session per
    webhook request.
    """
    return await _infer_single_plant_for_organization_in_session(
        session, organization_id
    )


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if settings.telegram_bot_token is None or settings.telegram_webhook_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram is not configured",
        )

    expected = settings.telegram_webhook_secret.get_secret_value()
    if not x_telegram_bot_api_secret_token or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    # Authorization is organization-scoped since the telegram_allowed_user_id
    # column was added: which user is allowed to talk to this bot depends on
    # which organization the incoming chat belongs to (resolved from
    # `telegram_chat_id`), not on a single process-wide setting. So we must
    # resolve the organization *before* validating the sender.
    try:
        chat_id = extract_chat_id(payload)
    except TelegramUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    async with SessionFactory() as session:
        await set_platform_context(session)
        organization_id = await _resolve_telegram_organization(session, chat_id)
        await set_tenant_context(session, organization_id)
        allowed_user_id = await _resolve_telegram_allowed_user_id(session, organization_id)

    if allowed_user_id is None:
        # Fail closed: an organization without its own configured
        # telegram_allowed_user_id is rejected outright. We deliberately do
        # NOT fall back to the process-wide MPLACAS_TELEGRAM_ALLOWED_USER_ID
        # setting here — doing so would silently re-authorize that single
        # global user for every organization missing its own value, which is
        # exactly the cross-tenant bypass this column exists to close. The
        # global setting is only ever used as a one-time deploy-time backfill
        # (see migration 20260731_0027), never as a runtime fallback.
        if settings.telegram_allowed_user_id is not None:
            logger.warning(
                "telegram_organization_missing_allowed_user_id",
                extra={
                    "organization_id": str(organization_id),
                    "hint": (
                        "MPLACAS_TELEGRAM_ALLOWED_USER_ID is set but is not "
                        "used as a fallback for this organization; configure "
                        "telegram_allowed_user_id directly on the "
                        "organization row"
                    ),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram is not configured for this organization",
        )

    try:
        message = parse_authorized_update(
            payload,
            allowed_user_id=allowed_user_id,
            max_document_bytes=settings.telegram_document_max_bytes,
        )
    except TelegramUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    client = TelegramClient(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        timeout_seconds=settings.request_timeout_seconds,
    )

    if message.kind == "command":
        async with SessionFactory() as session:
            await set_tenant_context(session, organization_id)
            reply_text = await _handle_telegram_command(
                session, organization_id, message.text or ""
            )
            await session.commit()
        try:
            await client.send_message(message.chat_id, reply_text)
        except TelegramClientError as exc:
            raise HTTPException(
                status_code=502, detail="Telegram acknowledgement failed"
            ) from exc
        return {
            "accepted": True,
            "kind": "command",
            "command": message.text,
        }

    if message.kind == "text":
        if message.text is None:
            raise HTTPException(status_code=422, detail="text message has no content")
        if len(message.text.encode("utf-8")) > settings.bill_text_max_bytes:
            raise HTTPException(
                status_code=413,
                detail="bill text exceeds configured size limit",
            )
        try:
            bill = parse_equatorial_bill_text(message.text)
            async with SessionFactory() as session:
                await set_tenant_context(session, organization_id)
                plant_id = await _resolve_telegram_plant_scope(session, organization_id)
                plant_name = await _fetch_plant_name(session, plant_id)
                record = await UtilityBillRepository(session).create_pending(
                    bill,
                    plant_id=plant_id,
                    source_text=message.text,
                )
                await session.commit()
                reference_month = record.reference_month
            await client.send_message(
                message.chat_id, _pending_message(reference_month, plant_name)
            )
        except BillParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except TelegramClientError as exc:
            raise HTTPException(status_code=502, detail="Telegram acknowledgement failed") from exc
        return {"accepted": True, "kind": "text", "status": "pending_review"}

    if message.document is None:
        raise HTTPException(status_code=422, detail="document message has no file attached")
    try:
        downloaded = await client.download_file(
            message.document.file_id,
            max_bytes=settings.telegram_document_max_bytes,
        )
        source_text = await extract_pdf_text_isolated(
            downloaded.content,
            max_pages=settings.telegram_pdf_max_pages,
            max_text_bytes=settings.bill_text_max_bytes,
            timeout_seconds=settings.telegram_pdf_parse_timeout_seconds,
            cpu_seconds=settings.telegram_pdf_parse_cpu_seconds,
            memory_bytes=settings.telegram_pdf_parse_memory_bytes,
        )
        processed = process_pdf_bill(
            downloaded.content,
            extract_text=lambda _: source_text,
            max_text_bytes=settings.bill_text_max_bytes,
        )
        async with SessionFactory() as session:
            await set_tenant_context(session, organization_id)
            plant_id = await _resolve_telegram_plant_scope(session, organization_id)
            plant_name = await _fetch_plant_name(session, plant_id)
            record = await UtilityBillRepository(session).create_pending(
                processed.bill,
                plant_id=plant_id,
                source_text=source_text,
            )
            await session.commit()
            reference_month = record.reference_month
        await client.send_message(
            message.chat_id, _pending_message(reference_month, plant_name)
        )
    except (
        TelegramClientError,
        TelegramDocumentProcessingError,
        PdfTextExtractionError,
        BillParseError,
    ) as exc:
        raise HTTPException(status_code=422, detail="bill PDF could not be processed") from exc

    return {
        "accepted": True,
        "kind": "document",
        "status": "pending_review",
        "reference_month": reference_month,
    }
