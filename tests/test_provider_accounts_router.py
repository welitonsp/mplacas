"""Rotas da conexão com o fabricante do inversor (ADR-091, fase 5)."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.providers.router as provider_router
from mplacas.audit.db_models import AuditEventRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.secret_box import KEY_BYTES, SecretBox
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Device, Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import ProviderAccountService, ProviderLogin
from mplacas.providers.base import ProviderAuthError, ProviderSchemaError, ProviderUnavailableError
from mplacas.providers.db_models import ProviderAccountRecord

KEY = base64.b64encode(b"\x09" * KEY_BYTES).decode()
PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-0000000000f2")
LOGIN = "cliente@example.com"
PASSWORD = "s3nh4-do-inversor"
URL = f"/plants/{PLANT_A}/provider-account"


async def _setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    async with factory() as session:
        session.add_all(
            [
                OrganizationRecord(id=org_a, name="A", slug=f"a-{org_a.hex[:8]}", active=True),
                OrganizationRecord(id=org_b, name="B", slug=f"b-{org_b.hex[:8]}", active=True),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Plant(id=PLANT_A, organization_id=org_a, name="Casa"),
                Plant(id=PLANT_B, organization_id=org_b, name="Vizinho"),
            ]
        )
        await session.commit()
    return factory, engine, org_a, org_b


class FakeVerifier:
    def __init__(self, serials=("SN-1",), error: Exception | None = None) -> None:
        self.serials = list(serials)
        self.error = error
        self.calls: list[ProviderLogin] = []

    async def __call__(self, provider: str, credentials: ProviderLogin) -> list[str]:
        self.calls.append(credentials)
        if self.error is not None:
            raise self.error
        return self.serials


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv("MPLACAS_PROVIDER_SECRET_KEYS", f"1:{KEY}")
    get_settings.cache_clear()
    factory, engine, org_a, org_b = asyncio.run(_setup())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(provider_router, "SessionFactory", factory)
    verifier = FakeVerifier()
    monkeypatch.setattr(provider_router, "verify_provider_account", verifier)
    tokens = {
        "a_admin": encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value),
        "a_read": encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value),
        "b_admin": encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value),
    }
    with TestClient(app) as client:
        yield client, factory, tokens, verifier
    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(**overrides) -> dict[str, str]:
    return {"login": LOGIN, "password": PASSWORD, **overrides}


async def _records(factory) -> list[ProviderAccountRecord]:
    async with factory() as session:
        return list(await session.scalars(select(ProviderAccountRecord)))


async def _audit(factory) -> list[AuditEventRecord]:
    async with factory() as session:
        return list(await session.scalars(select(AuditEventRecord)))


def test_admin_connects_after_the_provider_accepts_the_login(env, caplog) -> None:
    client, factory, tokens, verifier = env

    with caplog.at_level(logging.DEBUG):
        response = client.put(
            URL, json=_body(login=f"  {LOGIN} "), headers=_auth(tokens["a_admin"])
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CONECTADA"
    assert body["login_hint"] == "cl***@example.com"
    assert body["devices_found"] == 1
    assert verifier.calls[0].login == LOGIN
    rendered = response.text + caplog.text
    assert PASSWORD not in rendered and LOGIN not in rendered

    records = asyncio.run(_records(factory))
    assert len(records) == 1 and records[0].last_success_at is not None
    box = SecretBox.from_keyring(f"1:{KEY}")
    assert ProviderAccountService(None, box).open(records[0]).password == PASSWORD  # type: ignore[arg-type]
    events = asyncio.run(_audit(factory))
    assert [e.action for e in events] == ["provider_account.saved"]
    assert PASSWORD not in str(events[0].details) and LOGIN not in str(events[0].details)


def test_status_never_exposes_the_login_or_password(env) -> None:
    client, _, tokens, _ = env
    assert client.get(URL, headers=_auth(tokens["a_read"])).json() == {
        "status": "SEM_CONEXAO",
        "provider": None,
        "login_hint": None,
        "connected_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "devices_found": None,
    }
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    response = client.get(URL, headers=_auth(tokens["a_read"]))

    assert response.status_code == 200
    assert response.json()["status"] == "CONECTADA"
    assert PASSWORD not in response.text and LOGIN not in response.text
    assert "ciphertext" not in response.text and "fingerprint" not in response.text


@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        (ProviderAuthError("Credenciais NEPViewer recusadas"), 422, "provider_login_failed"),
        (ProviderSchemaError("envelope de erro"), 422, "provider_login_failed"),
        (ProviderUnavailableError("fora do ar"), 503, "provider_unavailable"),
    ],
)
def test_refused_or_unreachable_login_is_never_saved(env, error, code, detail) -> None:
    client, factory, tokens, verifier = env
    verifier.error = error

    response = client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    assert response.status_code == code
    assert response.json() == {"detail": detail}
    assert asyncio.run(_records(factory)) == []


def test_read_role_cannot_connect_or_disconnect(env) -> None:
    client, factory, tokens, verifier = env

    assert client.put(URL, json=_body(), headers=_auth(tokens["a_read"])).status_code == 403
    assert client.delete(URL, headers=_auth(tokens["a_read"])).status_code == 403
    assert verifier.calls == []


def test_other_organization_gets_404_for_every_verb(env) -> None:
    client, factory, tokens, verifier = env
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))
    verifier.calls.clear()

    for method in ("get", "put", "delete"):
        kwargs = {"json": _body()} if method == "put" else {}
        response = getattr(client, method)(URL, headers=_auth(tokens["b_admin"]), **kwargs)
        assert response.status_code == 404, method
    assert verifier.calls == []
    assert asyncio.run(_records(factory))[0].active


def test_inverters_of_another_plant_block_the_connection(env) -> None:
    client, factory, tokens, verifier = env

    async def _seed_device() -> None:
        async with factory() as session:
            session.add(Device(plant_id=PLANT_B, provider="NEPVIEWER", serial_number="SN-1"))
            await session.commit()

    asyncio.run(_seed_device())

    response = client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}
    assert asyncio.run(_records(factory)) == []


def test_same_account_on_another_plant_is_refused(env, monkeypatch) -> None:
    client, factory, tokens, verifier = env
    verifier.serials = []
    client.put(
        f"/plants/{PLANT_B}/provider-account", json=_body(), headers=_auth(tokens["b_admin"])
    )

    response = client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_account_in_use"}


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"login": "  ", "password": PASSWORD}, "provider_login_invalid"),
        ({"login": LOGIN, "password": ""}, "provider_password_invalid"),
        ({"login": LOGIN, "password": "x" * 257}, "provider_password_invalid"),
    ],
)
def test_invalid_input_is_refused_without_echoing_it(env, body, detail) -> None:
    client, factory, tokens, verifier = env

    response = client.put(URL, json=body, headers=_auth(tokens["a_admin"]))

    assert response.status_code == 422
    assert response.json() == {"detail": detail}
    assert PASSWORD not in response.text and "xxxx" not in response.text
    assert verifier.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"login": LOGIN, "passwd": PASSWORD},  # campo digitado errado
        {"login": LOGIN, "password": PASSWORD, "extra": PASSWORD},
        {"login": [PASSWORD], "password": "x"},
        {"login": LOGIN, "password": {"valor": PASSWORD}},
        {"login": LOGIN, "password": 12345},
        {"provider": "SOLIS", "login": LOGIN, "password": PASSWORD},
        [LOGIN, PASSWORD],
    ],
)
def test_malformed_bodies_never_echo_the_password(env, body) -> None:
    client, factory, tokens, verifier = env

    response = client.put(URL, json=body, headers=_auth(tokens["a_admin"]))

    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert LOGIN not in response.text
    assert "input" not in response.json()
    assert verifier.calls == []
    assert asyncio.run(_records(factory)) == []


def test_non_json_and_oversized_bodies_are_refused(env) -> None:
    client, _, tokens, verifier = env
    headers = {**_auth(tokens["a_admin"]), "Content-Type": "application/json"}

    assert (
        client.put(URL, content=b"{nao-json " + PASSWORD.encode(), headers=headers).status_code
        == 422
    )
    big = client.put(URL, json=_body(password="x" * 5000), headers=_auth(tokens["a_admin"]))
    assert big.status_code == 413
    assert verifier.calls == []


def test_disconnect_wipes_the_secret_and_is_audited(env) -> None:
    client, factory, tokens, _ = env
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    response = client.delete(URL, headers=_auth(tokens["a_admin"]))

    assert response.status_code == 204
    record = asyncio.run(_records(factory))[0]
    assert not record.active and record.ciphertext is None
    assert client.get(URL, headers=_auth(tokens["a_admin"])).json()["status"] == "SEM_CONEXAO"
    assert client.delete(URL, headers=_auth(tokens["a_admin"])).status_code == 404
    assert [e.action for e in asyncio.run(_audit(factory))] == [
        "provider_account.saved",
        "provider_account.removed",
    ]


def test_missing_keyring_refuses_to_save(env, monkeypatch) -> None:
    client, factory, tokens, verifier = env
    monkeypatch.delenv("MPLACAS_PROVIDER_SECRET_KEYS")
    get_settings.cache_clear()

    response = client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 503
    assert response.json() == {"detail": "provider_secret_keys_not_configured"}
    assert verifier.calls == []
    assert asyncio.run(_records(factory)) == []


def test_failed_collection_shows_as_failure(env) -> None:
    client, factory, tokens, _ = env
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    async def _fail() -> None:
        async with factory() as session:
            service = ProviderAccountService(session, SecretBox.from_keyring(f"1:{KEY}"))
            record = await service.get(PLANT_A)
            assert record is not None
            await service.record_failure(record, code="ProviderAuthError")
            await session.commit()

    asyncio.run(_fail())

    body = client.get(URL, headers=_auth(tokens["a_read"])).json()
    assert body["status"] == "FALHA"
    assert "ProviderAuthError" not in str(body)


def test_verification_attempts_are_rate_limited_per_plant(env) -> None:
    client, factory, tokens, verifier = env
    verifier.error = ProviderAuthError("recusado")

    codes = [
        client.put(URL, json=_body(), headers=_auth(tokens["a_admin"])).status_code
        for _ in range(provider_router.VERIFY_LIMIT + 1)
    ]

    assert codes == [422] * provider_router.VERIFY_LIMIT + [429]
    assert len(verifier.calls) == provider_router.VERIFY_LIMIT
    refusals = [
        e for e in asyncio.run(_audit(factory)) if e.action == "provider_account.verify_failed"
    ]
    assert len(refusals) == provider_router.VERIFY_LIMIT
    assert all(
        e.details == {"provider": "NEPVIEWER", "reason": "provider_login_failed"} for e in refusals
    )
    assert all(PASSWORD not in str(e.details) and LOGIN not in str(e.details) for e in refusals)


def test_refused_login_keeps_the_existing_connection(env) -> None:
    client, factory, tokens, verifier = env
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))
    verifier.error = ProviderAuthError("recusado")

    response = client.put(URL, json=_body(password="errada"), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 422
    record = asyncio.run(_records(factory))[0]
    box = SecretBox.from_keyring(f"1:{KEY}")
    assert ProviderAccountService(None, box).open(record).password == PASSWORD  # type: ignore[arg-type]


def test_reconnecting_the_same_plant_keeps_its_own_inverters(env) -> None:
    client, factory, tokens, verifier = env

    async def _seed() -> None:
        async with factory() as session:
            session.add(Device(plant_id=PLANT_A, provider="NEPVIEWER", serial_number="SN-1"))
            await session.commit()

    asyncio.run(_seed())
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    response = client.put(URL, json=_body(password="nova"), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 200
    record = asyncio.run(_records(factory))[0]
    assert record.rotated_at is not None
    box = SecretBox.from_keyring(f"1:{KEY}")
    assert ProviderAccountService(None, box).open(record).password == "nova"  # type: ignore[arg-type]


def test_disconnect_works_without_the_keyring(env, monkeypatch) -> None:
    client, factory, tokens, _ = env
    client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))
    monkeypatch.delenv("MPLACAS_PROVIDER_SECRET_KEYS")
    get_settings.cache_clear()

    assert client.delete(URL, headers=_auth(tokens["a_admin"])).status_code == 204
    assert asyncio.run(_records(factory))[0].ciphertext is None


def test_status_requires_authentication(env) -> None:
    client, *_ = env

    assert client.get(URL).status_code == 401
