"""ADR-069 § E3: ``/usinas`` and ``/usina <nome>`` Telegram commands, and the
plant-naming bill confirmation message.

Mirrors the fixture style of ``test_telegram_webhook_cross_tenant.py``: an
in-memory SQLite engine, a stubbed ``TelegramClient`` (so assertions can
inspect what would have been sent to the human), and a stubbed bill parser
(the parsing itself is covered elsewhere).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.telegram.router as telegram_router
from mplacas.core.config import get_settings
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

WEBHOOK_SECRET = "test-telegram-webhook-secret"
CHAT_ID = 2001
USER_ID = 2001


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One organization, two plants: ``Matriz`` (default) and ``Filial
    Norte``. Returns ``(organization_id, matriz_id, filial_norte_id)``."""
    async with factory() as session:
        organization_id = uuid.uuid4()
        matriz_id = uuid.uuid4()
        filial_norte_id = uuid.uuid4()
        session.add_all(
            [
                Plant(id=matriz_id, organization_id=organization_id, name="Matriz — Telhado A"),
                Plant(id=filial_norte_id, organization_id=organization_id, name="Filial Norte"),
            ]
        )
        session.add(
            OrganizationRecord(
                id=organization_id,
                name="Org",
                slug=f"org-{organization_id.hex[:8]}",
                active=True,
                telegram_chat_id=CHAT_ID,
                telegram_allowed_user_id=USER_ID,
                default_plant_id=matriz_id,
            )
        )
        await session.commit()
        return organization_id, matriz_id, filial_norte_id


async def _add_plant(factory, organization_id: uuid.UUID, name: str) -> uuid.UUID:
    async with factory() as session:
        plant_id = uuid.uuid4()
        session.add(Plant(id=plant_id, organization_id=organization_id, name=name))
        await session.commit()
        return plant_id


class _StubTelegramClient:
    def __init__(self, *, bot_token: str, timeout_seconds: float = 20.0) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def download_file(self, file_id: str, *, max_bytes: int):
        from mplacas.telegram.client import DownloadedTelegramFile

        return DownloadedTelegramFile(content=b"%PDF-1.4 stub", file_path="stub.pdf")


@pytest.fixture
def commands_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.delenv("MPLACAS_TELEGRAM_ALLOWED_USER_ID", raising=False)
    get_settings.cache_clear()

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(telegram_router, "SessionFactory", factory)

    stub_client = _StubTelegramClient(bot_token="test-bot-token")
    monkeypatch.setattr(
        telegram_router, "TelegramClient", lambda **_kwargs: stub_client
    )

    def fake_parse_equatorial_bill_text(text: str):
        return object()

    monkeypatch.setattr(
        telegram_router, "parse_equatorial_bill_text", fake_parse_equatorial_bill_text
    )

    async def fake_extract_pdf_text_isolated(content, **_kwargs):
        return "fatura texto valido"

    monkeypatch.setattr(
        telegram_router, "extract_pdf_text_isolated", fake_extract_pdf_text_isolated
    )

    def fake_process_pdf_bill(content, *, extract_text, max_text_bytes):
        class _Processed:
            bill = object()

        return _Processed()

    monkeypatch.setattr(telegram_router, "process_pdf_bill", fake_process_pdf_bill)

    async def fake_create_pending(self, bill, *, plant_id, source_text):
        class _Record:
            reference_month = "2026-07"

        return _Record()

    monkeypatch.setattr(
        "mplacas.billing.repository.UtilityBillRepository.create_pending",
        fake_create_pending,
    )

    organization_id, matriz_id, filial_norte_id = asyncio.run(_seed(factory))

    yield factory, organization_id, matriz_id, filial_norte_id, stub_client

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _command_update(text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "from": {"id": USER_ID},
            "chat": {"id": CHAT_ID, "type": "private"},
            "text": text,
        },
    }


def _text_update(text: str) -> dict:
    return _command_update(text)


def _document_update() -> dict:
    return {
        "update_id": 1,
        "message": {
            "from": {"id": USER_ID},
            "chat": {"id": CHAT_ID, "type": "private"},
            "document": {
                "file_id": "file-1",
                "file_name": "fatura.pdf",
                "mime_type": "application/pdf",
                "file_size": 1024,
            },
        },
    }


def _post(client: TestClient, payload: dict):
    return client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )


async def _read_default_plant_id(factory, organization_id: uuid.UUID) -> uuid.UUID | None:
    async with factory() as session:
        return (
            await session.execute(
                select(OrganizationRecord.default_plant_id).where(
                    OrganizationRecord.id == organization_id
                )
            )
        ).scalar_one_or_none()


def test_usinas_command_lists_plants_marking_the_default(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _command_update("/usinas"))

    assert response.status_code == 202, response.text
    assert len(stub_client.sent) == 1
    sent_chat_id, sent_text = stub_client.sent[0]
    assert sent_chat_id == CHAT_ID
    assert "Matriz — Telhado A (padrão)" in sent_text
    filial_line = next(
        line for line in sent_text.splitlines() if line.strip().startswith("- Filial Norte")
    )
    assert "(padrão)" not in filial_line


def test_usina_switches_the_default_plant_by_exact_name(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _command_update("/usina Filial Norte"))

    assert response.status_code == 202, response.text
    default_plant_id = asyncio.run(_read_default_plant_id(factory, organization_id))
    assert default_plant_id == filial_norte_id
    assert len(stub_client.sent) == 1
    assert "Filial Norte" in stub_client.sent[0][1]
    assert "Usina ativa agora" in stub_client.sent[0][1]


def test_usina_switches_the_default_plant_by_unique_prefix(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _command_update("/usina Filial"))

    assert response.status_code == 202, response.text
    default_plant_id = asyncio.run(_read_default_plant_id(factory, organization_id))
    assert default_plant_id == filial_norte_id


def test_usina_ambiguous_prefix_does_not_switch(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    asyncio.run(_add_plant(factory, organization_id, "Filial Sul"))
    client = TestClient(app)

    response = _post(client, _command_update("/usina Filial"))

    assert response.status_code == 202, response.text
    default_plant_id = asyncio.run(_read_default_plant_id(factory, organization_id))
    assert default_plant_id == matriz_id  # unchanged
    sent_text = stub_client.sent[0][1]
    assert "Filial Norte" in sent_text
    assert "Filial Sul" in sent_text


def test_usina_unknown_name_does_not_switch(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _command_update("/usina Inexistente"))

    assert response.status_code == 202, response.text
    default_plant_id = asyncio.run(_read_default_plant_id(factory, organization_id))
    assert default_plant_id == matriz_id  # unchanged
    assert "Não encontrei essa usina" in stub_client.sent[0][1]


def test_usina_without_argument_behaves_like_usinas(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _command_update("/usina"))

    assert response.status_code == 202, response.text
    assert "Usinas da sua conta" in stub_client.sent[0][1]


def test_unknown_command_responds_with_help_text_not_http_error(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _command_update("/foo"))

    assert response.status_code == 202, response.text
    assert "não reconhecido" in stub_client.sent[0][1] or "Comando" in stub_client.sent[0][1]


def test_bill_text_message_names_the_plant_it_was_filed_under(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _text_update("fatura texto valido"))

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending_review"
    assert len(stub_client.sent) == 1
    sent_text = stub_client.sent[0][1]
    assert "Matriz — Telhado A" in sent_text
    assert "2026-07" in sent_text
    assert "/usina <nome>" in sent_text


def test_bill_document_message_names_the_plant_it_was_filed_under(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    response = _post(client, _document_update())

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending_review"
    assert len(stub_client.sent) == 1
    sent_text = stub_client.sent[0][1]
    assert "Matriz — Telhado A" in sent_text
    assert "2026-07" in sent_text


def test_bill_after_switching_plant_goes_to_the_new_default(commands_setup) -> None:
    factory, organization_id, matriz_id, filial_norte_id, stub_client = commands_setup
    client = TestClient(app)

    switch_response = _post(client, _command_update("/usina Filial Norte"))
    assert switch_response.status_code == 202, switch_response.text

    bill_response = _post(client, _text_update("fatura texto valido"))
    assert bill_response.status_code == 202, bill_response.text

    assert len(stub_client.sent) == 2
    assert "Filial Norte" in stub_client.sent[1][1]
