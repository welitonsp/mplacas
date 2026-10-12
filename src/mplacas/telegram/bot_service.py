"""Database-backed operations behind the Telegram webhook.

``telegram.service`` validates the raw update (no I/O). This module owns what
needs the database: resolving which organization owns a chat, which user may
talk to the bot for it, the ``/usinas`` and ``/usina <nome>`` commands, and
registering a parsed bill as pending review. The router keeps the HTTP
concerns: webhook secret, settings, session/tenant context, the Telegram
client, PDF extraction and status codes.

Every query is scoped by ``organization_id`` in the ``WHERE`` clause, on top
of the RLS context the caller applies to the session.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.models import UtilityBill
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.tenancy import _infer_single_plant_for_organization_in_session
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord

COMMAND_HELP_MESSAGE = (
    "Comando não reconhecido. Use /usinas para listar as usinas da sua conta "
    "ou /usina <nome> para trocar a usina ativa."
)


class UnlinkedTelegramChatError(LookupError):
    """No organization links this Telegram ``chat_id``."""


@dataclass(frozen=True, slots=True)
class PendingBillReceipt:
    reference_month: str
    plant_name: str


def pending_bill_message(reference_month: str, plant_name: str) -> str:
    return (
        f"Fatura {reference_month} recebida e analisada, lançada na usina {plant_name}.\n"
        "Ela ficou pendente de revisão humana antes da consolidação.\n"
        "Usina errada? Use /usina <nome> e reenvie."
    )


def format_plant_list_message(
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


class TelegramBotService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_organization(self, chat_id: int) -> uuid.UUID:
        """Resolve the organization that owns a given Telegram ``chat_id``.

        Each organization links exactly one Telegram chat via
        ``OrganizationRecord.telegram_chat_id`` (see ADR/PR-6 of the
        multi-tenancy plan). Messages from an unrecognized chat are rejected
        outright — there is no global fallback plant/organization anymore.
        """
        organization_id = (
            await self._session.execute(
                select(OrganizationRecord.id).where(
                    OrganizationRecord.telegram_chat_id == chat_id
                )
            )
        ).scalar_one_or_none()
        if organization_id is None:
            raise UnlinkedTelegramChatError(chat_id)
        return organization_id

    async def allowed_user_id(self, organization_id: uuid.UUID) -> int | None:
        """Fetch the organization's own ``telegram_allowed_user_id``.

        Returns ``None`` if the organization hasn't configured one yet — the
        caller must fail closed in that case (see ``telegram_webhook``'s
        comment on why the process-wide ``MPLACAS_TELEGRAM_ALLOWED_USER_ID``
        setting is never used as a runtime fallback).
        """
        return (
            await self._session.execute(
                select(OrganizationRecord.telegram_allowed_user_id).where(
                    OrganizationRecord.id == organization_id
                )
            )
        ).scalar_one_or_none()

    async def resolve_bill_plant(self, organization_id: uuid.UUID) -> uuid.UUID:
        """Infer the single plant a bill from this organization belongs to.

        Reuses ``core.tenancy``'s organization-scoped plant inference (same
        409 semantics as ``resolve_admin_plant`` when the organization has
        zero or more than one plant and no default), against this service's
        session — no second connection per webhook request.
        """
        return await _infer_single_plant_for_organization_in_session(
            self._session, organization_id
        )

    async def register_pending_bill(
        self,
        organization_id: uuid.UUID,
        bill: UtilityBill,
        *,
        source_text: str,
    ) -> PendingBillReceipt:
        """Persist a parsed bill as pending human review (no commit)."""
        plant_id = await self.resolve_bill_plant(organization_id)
        plant_name = await self._plant_name(plant_id)
        record = await UtilityBillRepository(self._session).create_pending(
            bill,
            plant_id=plant_id,
            source_text=source_text,
        )
        return PendingBillReceipt(
            reference_month=record.reference_month, plant_name=plant_name
        )

    async def handle_command(self, organization_id: uuid.UUID, command_text: str) -> str:
        """Dispatch a Telegram command (``/usinas``, ``/usina <nome>``, ...).

        Unknown commands return help text rather than raising — the webhook
        keeps responding 202 regardless of whether the command was recognized
        (see ADR-069 § E.5).
        """
        parts = command_text.strip().split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        argument = parts[1].strip() if len(parts) > 1 else ""

        if command in ("/usinas", "/usina") and not argument:
            plants = await self._list_plants(organization_id)
            default_plant_id = await self._default_plant_id(organization_id)
            return format_plant_list_message(plants, default_plant_id)

        if command == "/usina":
            return await self._switch_default_plant(organization_id, argument)

        return COMMAND_HELP_MESSAGE

    async def find_plants_by_name(
        self, organization_id: uuid.UUID, name: str
    ) -> list[tuple[uuid.UUID, str]]:
        """Resolve ``name`` against the organization's plants.

        Case-insensitive exact match takes precedence over a case-insensitive
        prefix match (``ILIKE`` anchored at the start). Returns the exact
        match alone when exactly one exists; otherwise returns every prefix
        candidate (zero, one, or many), leaving ambiguity/absence handling to
        the caller.
        """
        clean_name = name.strip()

        exact_result = await self._session.execute(
            select(Plant.id, Plant.name).where(
                Plant.organization_id == organization_id,
                func.lower(Plant.name) == clean_name.lower(),
            )
        )
        exact = [(row[0], row[1]) for row in exact_result]
        if len(exact) == 1:
            return exact

        escaped = clean_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        prefix_result = await self._session.execute(
            select(Plant.id, Plant.name)
            .where(
                Plant.organization_id == organization_id,
                Plant.name.ilike(f"{escaped}%", escape="\\"),
            )
            .order_by(Plant.name, Plant.id)
        )
        return [(row[0], row[1]) for row in prefix_result]

    async def _switch_default_plant(self, organization_id: uuid.UUID, name: str) -> str:
        candidates = await self.find_plants_by_name(organization_id, name)
        if not candidates:
            return "Não encontrei essa usina. Use /usinas para ver a lista."
        if len(candidates) > 1:
            names = ", ".join(candidate_name for _, candidate_name in candidates)
            return (
                "Encontrei mais de uma usina com esse nome: "
                f"{names}. Use /usina <nome completo> para escolher."
            )
        plant_id, plant_name = candidates[0]
        organization = await self._session.get(OrganizationRecord, organization_id)
        if organization is not None:
            organization.default_plant_id = plant_id
            await self._session.flush()
        return f"Usina ativa agora: {plant_name}. As próximas faturas serão lançadas nela."

    async def _list_plants(self, organization_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        result = await self._session.execute(
            select(Plant.id, Plant.name)
            .where(Plant.organization_id == organization_id)
            .order_by(Plant.name, Plant.id)
        )
        return [(row[0], row[1]) for row in result]

    async def _default_plant_id(self, organization_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self._session.execute(
                select(OrganizationRecord.default_plant_id).where(
                    OrganizationRecord.id == organization_id
                )
            )
        ).scalar_one_or_none()

    async def _plant_name(self, plant_id: uuid.UUID) -> str:
        """Fetch a plant's ``name`` for use in human-facing messages.

        Falls back to a generic label rather than raising if the row somehow
        vanished between resolution and this lookup — the bill is written
        against ``plant_id`` regardless, so the confirmation must not fail.
        """
        name = (
            await self._session.execute(select(Plant.name).where(Plant.id == plant_id))
        ).scalar_one_or_none()
        return name or "usina"
