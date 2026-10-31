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
from mplacas.providers.base import (
    PlantProfile,
    ProviderAuthError,
    ProviderSchemaError,
    ProviderUnavailableError,
)
from mplacas.providers.router import ProviderInspection
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
    def __init__(
        self,
        serials=("SN-1",),
        error: Exception | None = None,
        profile: PlantProfile | None = None,
    ) -> None:
        self.serials = list(serials)
        self.error = error
        self.profile = profile
        self.calls: list[ProviderLogin] = []

    async def __call__(self, provider: str, credentials: ProviderLogin) -> ProviderInspection:
        self.calls.append(credentials)
        if self.error is not None:
            raise self.error
        return ProviderInspection(self.serials, self.profile)


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


def test_growatt_connection_uses_the_chosen_brand(env) -> None:
    client, factory, tokens, verifier = env
    calls: list[str] = []

    async def _verify(provider: str, credentials: ProviderLogin) -> ProviderInspection:
        calls.append(provider)
        return ProviderInspection(["GW-PLANT-777"])

    import mplacas.providers.router as router_module

    original = router_module.verify_provider_account
    router_module.verify_provider_account = _verify
    try:
        response = client.put(
            URL, json=_body(provider="GROWATT", login="rogerio"), headers=_auth(tokens["a_admin"])
        )
    finally:
        router_module.verify_provider_account = original

    assert response.status_code == 200
    assert response.json()["provider"] == "GROWATT"
    assert calls == ["GROWATT"]
    assert asyncio.run(_records(factory))[0].provider == "GROWATT"


def test_brand_rate_limit_asks_to_wait(env) -> None:
    from mplacas.providers.base import ProviderRateLimitedError

    client, factory, tokens, verifier = env
    verifier.error = ProviderRateLimitedError("507")

    response = client.put(URL, json=_body(provider="GROWATT"), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 503
    assert response.json() == {"detail": "provider_rate_limited"}
    assert asyncio.run(_records(factory)) == []


# --- ADR-093 § 7: a usina nasce da conexão e se preenche sozinha -------------

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

CONNECT = "/plants/connect"
PROFILE = PlantProfile(
    name="Usina do Rogério",
    installed_power_kwp=Decimal("5.4"),
    latitude=Decimal("-17.744100"),
    longitude=Decimal("-48.625200"),
    city="Caldas Novas",
    commissioned_on=date(2021, 3, 15),
)


def _empty_org(factory) -> uuid.UUID:
    org_id = uuid.uuid4()

    async def _seed() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(id=org_id, name="Novo", slug=f"n-{org_id.hex[:8]}", active=True)
            )
            await session.commit()

    asyncio.run(_seed())
    return org_id


def _token(org_id: uuid.UUID, role: OperationsRole = OperationsRole.ADMIN) -> dict[str, str]:
    return _auth(encode_access_token(uuid.uuid4(), org_id, role.value))


async def _plants_of(factory, org_id) -> list[Plant]:
    async with factory() as session:
        return list(await session.scalars(select(Plant).where(Plant.organization_id == org_id)))


async def _org(factory, org_id) -> OrganizationRecord:
    async with factory() as session:
        return await session.get(OrganizationRecord, org_id)


def test_first_connection_creates_and_fills_the_plant(env) -> None:
    client, factory, _tokens, verifier = env
    verifier.serials = ["GW-PLANT-777"]
    verifier.profile = PROFILE
    org_id = _empty_org(factory)

    response = client.post(
        CONNECT, json=_body(provider="GROWATT", login="rogerio"), headers=_token(org_id)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["plant_name"] == "Usina do Rogério"
    assert body["connection"]["status"] == "CONECTADA"
    assert body["auto_filled"]["dc_capacity_kwp"] == "BRAND"
    assert body["auto_filled"]["array_tilt_degrees"] == "ESTIMATE"
    assert "commissioned_on" not in body["auto_filled"]
    assert PASSWORD not in response.text

    plants = asyncio.run(_plants_of(factory, org_id))
    assert len(plants) == 1
    plant = plants[0]
    assert plant.installed_power_kwp == Decimal("5.400")
    assert plant.commissioned_on is None
    assert asyncio.run(_org(factory, org_id)).default_plant_id == plant.id
    assert asyncio.run(_records(factory))[-1].plant_id == plant.id

    actions = [event.action for event in asyncio.run(_audit(factory))]
    assert "plant.created_from_connection" in actions
    assert all(PASSWORD not in repr(e.details) for e in asyncio.run(_audit(factory)))


def test_first_connection_without_profile_uses_default_name(env) -> None:
    client, factory, _tokens, verifier = env
    org_id = _empty_org(factory)

    response = client.post(CONNECT, json=_body(), headers=_token(org_id))

    assert response.status_code == 201
    assert response.json()["plant_name"] == "Minha usina"
    assert response.json()["auto_filled"] == {}


def test_first_connection_refused_when_org_already_has_a_plant(env) -> None:
    client, _factory, tokens, verifier = env
    response = client.post(CONNECT, json=_body(), headers=_auth(tokens["a_admin"]))
    assert response.status_code == 409
    assert response.json()["detail"] == "plant_already_exists"
    assert verifier.calls == []  # nem chega a entrar na marca


def test_first_connection_wrong_password_creates_nothing(env) -> None:
    client, factory, _tokens, verifier = env
    verifier.error = ProviderAuthError("recusado")
    org_id = _empty_org(factory)

    response = client.post(CONNECT, json=_body(), headers=_token(org_id))

    assert response.status_code == 422
    assert response.json()["detail"] == "provider_login_failed"
    assert asyncio.run(_plants_of(factory, org_id)) == []
    refusal = [e for e in asyncio.run(_audit(factory)) if e.action.endswith("verify_failed")]
    assert refusal[-1].resource_type == "organization"
    assert refusal[-1].resource_id == str(org_id)


def test_first_connection_is_rate_limited_per_organization(env) -> None:
    client, factory, _tokens, verifier = env
    verifier.error = ProviderAuthError("recusado")
    org_id = _empty_org(factory)
    for _ in range(provider_router.VERIFY_LIMIT):
        client.post(CONNECT, json=_body(), headers=_token(org_id))

    response = client.post(CONNECT, json=_body(), headers=_token(org_id))

    assert response.status_code == 429


def test_first_connection_requires_org_admin(env) -> None:
    client, factory, _tokens, verifier = env
    org_id = _empty_org(factory)
    assert (
        client.post(CONNECT, json=_body(), headers=_token(org_id, OperationsRole.READ)).status_code
        == 403
    )
    assert client.post(CONNECT, json=_body()).status_code == 401


def test_first_connection_refuses_inverter_of_another_plant(env) -> None:
    client, factory, tokens, verifier = env
    # a usina A já está com o inversor SN-1
    assert client.put(URL, json=_body(), headers=_auth(tokens["a_admin"])).status_code == 200

    async def _seed_device() -> None:
        async with factory() as session:
            session.add(Device(plant_id=PLANT_A, provider="NEPVIEWER", serial_number="SN-1"))
            await session.commit()

    asyncio.run(_seed_device())
    org_id = _empty_org(factory)

    response = client.post(CONNECT, json=_body(login="outro@example.com"), headers=_token(org_id))

    assert response.status_code == 409
    assert response.json()["detail"] == "provider_inverter_in_another_plant"
    assert asyncio.run(_plants_of(factory, org_id)) == []


def test_reconnecting_fills_only_empty_fields(env) -> None:
    client, factory, tokens, verifier = env
    verifier.profile = PROFILE

    async def _set_power() -> None:
        async with factory() as session:
            plant = await session.get(Plant, PLANT_A)
            plant.installed_power_kwp = Decimal("7.2")
            await session.commit()

    asyncio.run(_set_power())

    response = client.put(URL, json=_body(), headers=_auth(tokens["a_admin"]))

    assert response.status_code == 200

    async def _plant() -> Plant:
        async with factory() as session:
            return await session.get(Plant, PLANT_A)

    plant = asyncio.run(_plant())
    assert plant.name == "Casa"  # nome da usina existente não muda
    assert plant.installed_power_kwp == Decimal("7.200")  # o que o dono informou fica
    assert plant.latitude == Decimal("-17.744100")
    assert plant.auto_filled == {
        "location": "BRAND",
        "array_tilt_degrees": "ESTIMATE",
        "array_azimuth_degrees": "ESTIMATE",
        "module_technology": "ESTIMATE",
    }
