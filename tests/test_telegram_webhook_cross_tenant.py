"""PR-6: organization-scoped Telegram webhook.

Verifies that ``telegram.router`` resolves the plant scope for a bill intake
strictly from the organization linked to the *incoming* Telegram chat
(``OrganizationRecord.telegram_chat_id``), never from a global "the only
plant in the system" fallback — in the same spirit as
``test_climate_tenant_boundaries.py``, adapted for the webhook flow (there is
no ``OperationsPrincipal``/bearer token here; identity comes from the chat
the message originated from).

Note: ``telegram.service.parse_authorized_update`` only accepts messages from
a *private* chat, where Telegram guarantees ``chat_id == from.id`` — and only
from the single ``telegram_allowed_user_id`` configured for the whole
process. That authentication layer is unchanged by this PR (see the task
description). So each scenario below configures
``MPLACAS_TELEGRAM_ALLOWED_USER_ID`` to match the chat/org under test before
issuing its request(s) — mirroring how, operationally, each organization
would authorize its own Telegram user against this single-process bot.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.telegram.router as telegram_router
from mplacas.core.config import get_settings
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

WEBHOOK_SECRET = "test-telegram-webhook-secret"

CHAT_A = 1001
CHAT_B = 1002
CHAT_UNKNOWN = 9999


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID]:
    """Org A: chat A linked, exactly one plant. Org B: chat B linked, no plant."""
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a,
                    name="Org A",
                    slug=f"org-a-{org_a.hex[:8]}",
                    active=True,
                    telegram_chat_id=CHAT_A,
                ),
                OrganizationRecord(
                    id=org_b,
                    name="Org B",
                    slug=f"org-b-{org_b.hex[:8]}",
                    active=True,
                    telegram_chat_id=CHAT_B,
                ),
            ]
        )
        session.add(Plant(id=uuid.uuid4(), organization_id=org_a, name="Plant A"))
        await session.commit()
        return org_a, org_b


class _StubTelegramClient:
    def __init__(self, *, bot_token: str, timeout_seconds: float = 20.0) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
def webhook_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "test-bot-token")

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(telegram_router, "SessionFactory", factory)
    monkeypatch.setattr(telegram_router, "TelegramClient", _StubTelegramClient)

    def fake_parse_equatorial_bill_text(text: str):
        return object()

    monkeypatch.setattr(
        telegram_router, "parse_equatorial_bill_text", fake_parse_equatorial_bill_text
    )

    org_a, org_b = asyncio.run(_seed(factory))

    yield org_a, org_b

    get_settings.cache_clear()


def _authorize_as_chat(monkeypatch, chat_id: int) -> None:
    """Configure the single globally-authorized Telegram user id for a request.

    Telegram private chats always have ``chat_id == from.id``, so
    "authorize chat X" and "authorize user X" are the same env var here.
    """
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALLOWED_USER_ID", str(chat_id))
    get_settings.cache_clear()


def _text_update(chat_id: int, text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "from": {"id": chat_id},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


def _post(client: TestClient, payload: dict):
    return client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )


def test_webhook_rejects_message_from_unlinked_chat(webhook_setup, monkeypatch) -> None:
    _authorize_as_chat(monkeypatch, CHAT_UNKNOWN)
    client = TestClient(app)

    response = _post(client, _text_update(CHAT_UNKNOWN, "qualquer texto de fatura"))

    assert response.status_code == 403
    assert "not linked to any organization" in response.json()["detail"]


def test_webhook_resolves_single_plant_for_linked_organization(
    webhook_setup, monkeypatch
) -> None:
    org_a, _org_b = webhook_setup
    _authorize_as_chat(monkeypatch, CHAT_A)
    client = TestClient(app)

    captured: dict = {}

    async def fake_create_pending(self, bill, *, plant_id, source_text):
        captured["plant_id"] = plant_id

        class _Record:
            reference_month = "2026-07"

        return _Record()

    monkeypatch.setattr(
        "mplacas.billing.repository.UtilityBillRepository.create_pending",
        fake_create_pending,
    )

    response = _post(client, _text_update(CHAT_A, "fatura texto valido"))

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending_review"
    assert captured["plant_id"] is not None


def test_webhook_rejects_organization_with_zero_plants(webhook_setup, monkeypatch) -> None:
    _org_a, _org_b = webhook_setup
    _authorize_as_chat(monkeypatch, CHAT_B)
    client = TestClient(app)

    response = _post(client, _text_update(CHAT_B, "fatura texto valido"))

    assert response.status_code == 409


def test_webhook_organizations_stay_isolated_by_chat_id(webhook_setup, monkeypatch) -> None:
    """Org A's chat resolves org A's plant; org B's chat (0 plants) never does,
    and never falls back to org A's plant either."""
    org_a, org_b = webhook_setup

    resolved_plant_ids: list[uuid.UUID] = []

    async def fake_create_pending(self, bill, *, plant_id, source_text):
        resolved_plant_ids.append(plant_id)

        class _Record:
            reference_month = "2026-07"

        return _Record()

    monkeypatch.setattr(
        "mplacas.billing.repository.UtilityBillRepository.create_pending",
        fake_create_pending,
    )

    client = TestClient(app)

    _authorize_as_chat(monkeypatch, CHAT_A)
    response_a = _post(client, _text_update(CHAT_A, "fatura texto valido"))
    assert response_a.status_code == 202, response_a.text

    _authorize_as_chat(monkeypatch, CHAT_B)
    response_b = _post(client, _text_update(CHAT_B, "fatura texto valido"))
    assert response_b.status_code == 409

    assert len(resolved_plant_ids) == 1
