"""PR-6/PR-7: organization-scoped Telegram webhook routing *and*
authorization.

PR-6 resolved bill-intake plant scope strictly from the organization linked
to the incoming Telegram chat (``OrganizationRecord.telegram_chat_id``),
never from a global "the only plant in the system" fallback.

PR-7 (this file) closes the remaining authentication gap: before
``telegram_allowed_user_id`` was added to ``OrganizationRecord``, a single
process-wide ``MPLACAS_TELEGRAM_ALLOWED_USER_ID`` env var authorized *any*
chat linked to *any* organization — so a Telegram user legitimately
authorized for organization A's chat was also implicitly authorized for
organization B's chat, as long as both used the same bot process. Each
organization now configures its own ``telegram_allowed_user_id`` and the
webhook fails closed (403) for organizations without one, never falling back
to the global setting at request time (see ``telegram/router.py``).
"""

from __future__ import annotations

import asyncio
import logging
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
USER_A = 1001  # Telegram private chats always have chat_id == from.id
CHAT_B = 1002
USER_B = 1002
CHAT_UNKNOWN = 9999
CHAT_C = 1003  # linked organization, but with no telegram_allowed_user_id


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org A: chat A + user A, exactly one plant.

    Org B: chat B + user B, no plant.
    Org C: chat C linked, but no telegram_allowed_user_id configured.
    """
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        org_c = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a,
                    name="Org A",
                    slug=f"org-a-{org_a.hex[:8]}",
                    active=True,
                    telegram_chat_id=CHAT_A,
                    telegram_allowed_user_id=USER_A,
                ),
                OrganizationRecord(
                    id=org_b,
                    name="Org B",
                    slug=f"org-b-{org_b.hex[:8]}",
                    active=True,
                    telegram_chat_id=CHAT_B,
                    telegram_allowed_user_id=USER_B,
                ),
                OrganizationRecord(
                    id=org_c,
                    name="Org C",
                    slug=f"org-c-{org_c.hex[:8]}",
                    active=True,
                    telegram_chat_id=CHAT_C,
                    telegram_allowed_user_id=None,
                ),
            ]
        )
        session.add(Plant(id=uuid.uuid4(), organization_id=org_a, name="Plant A"))
        await session.commit()
        return org_a, org_b, org_c


class _StubTelegramClient:
    def __init__(self, *, bot_token: str, timeout_seconds: float = 20.0) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
def webhook_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.delenv("MPLACAS_TELEGRAM_ALLOWED_USER_ID", raising=False)
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(telegram_router, "SessionFactory", factory)
    monkeypatch.setattr(telegram_router, "TelegramClient", _StubTelegramClient)

    def fake_parse_equatorial_bill_text(text: str):
        return object()

    monkeypatch.setattr(
        telegram_router, "parse_equatorial_bill_text", fake_parse_equatorial_bill_text
    )

    org_a, org_b, org_c = asyncio.run(_seed(factory))

    yield org_a, org_b, org_c

    get_settings.cache_clear()


def _text_update(chat_id: int, user_id: int, text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "from": {"id": user_id},
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


def test_webhook_rejects_message_from_unlinked_chat(webhook_setup) -> None:
    client = TestClient(app)

    response = _post(client, _text_update(CHAT_UNKNOWN, CHAT_UNKNOWN, "qualquer texto de fatura"))

    assert response.status_code == 403
    assert "not linked to any organization" in response.json()["detail"]


def test_webhook_resolves_single_plant_for_linked_organization(
    webhook_setup, monkeypatch
) -> None:
    org_a, _org_b, _org_c = webhook_setup
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

    response = _post(client, _text_update(CHAT_A, USER_A, "fatura texto valido"))

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending_review"
    assert captured["plant_id"] is not None


def test_webhook_rejects_organization_with_zero_plants(webhook_setup) -> None:
    _org_a, _org_b, _org_c = webhook_setup
    client = TestClient(app)

    response = _post(client, _text_update(CHAT_B, USER_B, "fatura texto valido"))

    assert response.status_code == 409


def test_webhook_organizations_stay_isolated_by_allowed_user_id(
    webhook_setup, monkeypatch
) -> None:
    """Org A's user cannot act on org B's chat, and vice versa, even though
    both chats are correctly linked to their respective organizations."""
    client = TestClient(app)

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

    # Org A's authorized user hitting org B's chat: user_id mismatch for
    # org B's own telegram_allowed_user_id -> rejected, never falls through
    # to org A's plant/data.
    cross_payload = {
        "update_id": 1,
        "message": {
            "from": {"id": USER_A},
            "chat": {"id": CHAT_B, "type": "private"},
            "text": "fatura texto valido",
        },
    }
    response = _post(client, cross_payload)
    assert response.status_code == 403

    # Each organization's own user still works for its own chat.
    response_a = _post(client, _text_update(CHAT_A, USER_A, "fatura texto valido"))
    assert response_a.status_code == 202, response_a.text
    assert len(resolved_plant_ids) == 1


def test_webhook_fails_closed_for_organization_without_allowed_user_id(
    webhook_setup, caplog
) -> None:
    """Org C has a linked chat but no telegram_allowed_user_id configured:
    the webhook must reject the message (403), never falling back to the
    process-wide MPLACAS_TELEGRAM_ALLOWED_USER_ID setting."""
    client = TestClient(app)

    response = _post(client, _text_update(CHAT_C, CHAT_C, "fatura texto valido"))

    assert response.status_code == 403
    assert "not configured for this organization" in response.json()["detail"]


def test_webhook_logs_warning_when_global_setting_present_but_unused(
    webhook_setup, monkeypatch, caplog
) -> None:
    """When the legacy global MPLACAS_TELEGRAM_ALLOWED_USER_ID is still set,
    an organization missing its own telegram_allowed_user_id is still
    rejected (fail closed) but a warning nudges towards migrating the
    configuration — the global value is never used to authorize the
    request."""
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALLOWED_USER_ID", str(CHAT_C))
    get_settings.cache_clear()
    client = TestClient(app)

    with caplog.at_level(logging.WARNING, logger="mplacas.telegram.router"):
        response = _post(client, _text_update(CHAT_C, CHAT_C, "fatura texto valido"))

    assert response.status_code == 403
    assert any(
        "telegram_organization_missing_allowed_user_id" in record.message
        for record in caplog.records
    )
