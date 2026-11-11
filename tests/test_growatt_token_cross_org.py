"""A mesma conta Growatt (token) em duas organizações (suspeita de vazamento entre clientes).

Cada teste afirma a expectativa SEGURA: a segunda organização é recusada com 409
(``provider_inverter_in_another_plant`` ou ``provider_account_in_use``).

A impressão digital não pega o token (o login dele é aleatório por requisição,
``_token_login``) e os aparelhos (``devices``) só nascem na primeira coleta
(``SolarCollectionService._get_or_create_device``). Quem fecha a lacuna são as
reservas de ``provider_plant_claims``, gravadas na conexão (ADR-100).
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.providers.router as provider_router
from mplacas.audit.db_models import AuditEventRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.secret_box import KEY_BYTES
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, Device, MeterReading, Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN, ProviderLogin
from mplacas.providers.base import DailyEnergy as ProviderDailyEnergy
from mplacas.providers.base import DeviceOverview, SolarDevice, SolarProvider
from mplacas.providers.db_models import ProviderAccountRecord, ProviderPlantClaimRecord
from mplacas.providers.router import ProviderInspection
from mplacas.services.collection import CollectionPlantError, SolarCollectionService

KEY = base64.b64encode(b"\x09" * KEY_BYTES).decode()
PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-0000000000f2")
SERIAL = "GW-PLANT-1383141"
TOKEN = "token.da.usina.compartilhada"
URL_A = f"/plants/{PLANT_A}/provider-account"
URL_B = f"/plants/{PLANT_B}/provider-account"
PREVIEW = "/plants/connect/preview"
CONFIRM = "/plants/connect/confirm"
CONNECT = "/plants/connect"


async def _setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_fk_pragma(dbapi_conn, _record):  # CASCADE das reservas, como no teste do modelo
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
                Plant(id=PLANT_A, organization_id=org_a, name="Casa A"),
                Plant(id=PLANT_B, organization_id=org_b, name="Casa B"),
            ]
        )
        await session.commit()
    return factory, engine, org_a, org_b


class FakeVerifier:
    """A marca devolve sempre a mesma usina física, seja qual for a conta."""

    def __init__(self) -> None:
        self.serials = [SERIAL]
        self.calls: list[tuple[str, ProviderLogin]] = []

    async def __call__(self, provider: str, credentials: ProviderLogin) -> ProviderInspection:
        self.calls.append((provider, credentials))
        return ProviderInspection(list(self.serials), None)


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
    admins = {
        "a": _auth(encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)),
        "b": _auth(encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)),
    }
    with TestClient(app) as client:
        yield client, factory, admins, verifier
    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_body() -> dict[str, str]:
    return {"provider": "GROWATT_TOKEN", "password": TOKEN}


def _password_body() -> dict[str, str]:
    return {"provider": "GROWATT", "login": "rogerio", "password": "s3nh4-growatt"}


async def _records(factory) -> list[ProviderAccountRecord]:
    async with factory() as session:
        return list(await session.scalars(select(ProviderAccountRecord)))


async def _claims(factory) -> list[ProviderPlantClaimRecord]:
    async with factory() as session:
        return list(await session.scalars(select(ProviderPlantClaimRecord)))


async def _devices(factory) -> list[Device]:
    async with factory() as session:
        return list(await session.scalars(select(Device)))


def _seed_device(factory, plant_id: uuid.UUID, provider: str) -> None:
    """O que a primeira coleta (ou a leitura da madrugada) deixa em ``devices``."""

    async def _run() -> None:
        async with factory() as session:
            session.add(Device(plant_id=plant_id, provider=provider, serial_number=SERIAL))
            await session.commit()

    asyncio.run(_run())


def _empty_org(factory) -> tuple[uuid.UUID, dict[str, str]]:
    org_id = uuid.uuid4()

    async def _seed() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(id=org_id, name="Novo", slug=f"n-{org_id.hex[:8]}", active=True)
            )
            await session.commit()

    asyncio.run(_seed())
    return org_id, _auth(encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value))


def _put(client, url, body, headers):
    return client.put(url, json=body, headers=headers)


def _assert_refused(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["detail"] in {
        "provider_inverter_in_another_plant",
        "provider_account_in_use",
    }


# --- PUT /plants/{id}/provider-account -------------------------------------


def test_put_token_same_plant_in_two_orgs_before_collection_is_refused(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200
    assert asyncio.run(_devices(factory)) == []  # nada barra: a conexão não cria Device

    response = _put(client, URL_B, _token_body(), admins["b"])

    _assert_refused(response)
    assert len(asyncio.run(_records(factory))) == 1


def test_put_token_same_plant_in_two_orgs_second_is_refused_and_only_a_is_claimed(env) -> None:
    client, factory, admins, _ = env
    first = _put(client, URL_A, _token_body(), admins["a"])
    second = _put(client, URL_B, _token_body(), admins["b"])

    assert (first.status_code, second.status_code) == (200, 409)
    assert second.json() == {"detail": "provider_inverter_in_another_plant"}
    records = asyncio.run(_records(factory))
    assert [(r.plant_id, r.active) for r in records] == [(PLANT_A, True)]
    claims = asyncio.run(_claims(factory))
    assert [(c.plant_id, c.provider_family, c.serial_number) for c in claims] == [
        (PLANT_A, "GROWATT", SERIAL)
    ]
    assert asyncio.run(_devices(factory)) == []


def test_put_token_same_plant_after_first_collection_is_refused(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200
    _seed_device(factory, PLANT_A, GROWATT_TOKEN)

    response = _put(client, URL_B, _token_body(), admins["b"])

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}
    assert [r.plant_id for r in asyncio.run(_records(factory))] == [PLANT_A]


def test_put_password_in_a_then_token_in_b_before_collection_is_refused(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _password_body(), admins["a"]).status_code == 200

    response = _put(client, URL_B, _token_body(), admins["b"])

    _assert_refused(response)
    assert len(asyncio.run(_records(factory))) == 1


def test_put_token_in_a_then_password_in_b_before_collection_is_refused(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200

    response = _put(client, URL_B, _password_body(), admins["b"])

    _assert_refused(response)
    assert len(asyncio.run(_records(factory))) == 1


def test_put_password_in_a_then_token_in_b_after_collection_is_refused(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _password_body(), admins["a"]).status_code == 200
    _seed_device(factory, PLANT_A, GROWATT)  # a família Growatt confere junta

    response = _put(client, URL_B, _token_body(), admins["b"])

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}


# --- primeiro acesso: POST /plants/connect ---------------------------------


def test_connect_token_same_plant_in_two_new_orgs_before_collection_is_refused(env) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    _, head_2 = _empty_org(factory)
    assert client.post(CONNECT, json=_token_body(), headers=head_1).status_code == 201

    response = client.post(CONNECT, json=_token_body(), headers=head_2)

    _assert_refused(response)


def test_connect_token_same_plant_after_first_collection_is_refused(env) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    org_2, head_2 = _empty_org(factory)
    created = client.post(CONNECT, json=_token_body(), headers=head_1)
    assert created.status_code == 201
    _seed_device(factory, uuid.UUID(created.json()["plant_id"]), GROWATT_TOKEN)

    response = client.post(CONNECT, json=_token_body(), headers=head_2)

    assert response.status_code == 409
    assert response.json()["detail"] == "provider_inverter_in_another_plant"

    async def _plants() -> list[Plant]:
        async with factory() as session:
            return list(
                await session.scalars(select(Plant).where(Plant.organization_id == org_2))
            )

    assert asyncio.run(_plants()) == []


def test_connect_password_in_a_then_token_in_new_org_before_collection_is_refused(env) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    _, head_2 = _empty_org(factory)
    assert client.post(CONNECT, json=_password_body(), headers=head_1).status_code == 201

    response = client.post(CONNECT, json=_token_body(), headers=head_2)

    _assert_refused(response)


# --- primeiro acesso: prévia + confirmação ---------------------------------


def _preview_confirm(client, headers, body):
    preview = client.post(PREVIEW, json=body, headers=headers)
    if preview.status_code != 200:
        return preview
    data = preview.json()
    plant = {k: v for k, v in data["plant"].items() if k != "city"}
    return client.post(CONFIRM, json={"ticket": data["ticket"], "plant": plant}, headers=headers)


def test_preview_confirm_token_same_plant_in_two_new_orgs_before_collection_is_refused(
    env,
) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    _, head_2 = _empty_org(factory)
    assert _preview_confirm(client, head_1, _token_body()).status_code == 201

    response = _preview_confirm(client, head_2, _token_body())

    _assert_refused(response)


def test_preview_token_same_plant_after_first_collection_is_refused(env) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    _, head_2 = _empty_org(factory)
    created = _preview_confirm(client, head_1, _token_body())
    assert created.status_code == 201
    _seed_device(factory, uuid.UUID(created.json()["plant_id"]), GROWATT_TOKEN)

    response = client.post(PREVIEW, json=_token_body(), headers=head_2)

    assert response.status_code == 409
    assert response.json()["detail"] == "provider_inverter_in_another_plant"


def test_confirm_rechecks_inverter_so_a_stale_ticket_cannot_bypass_a_new_claim(env) -> None:
    """B abre a prévia antes de A conectar; quando A conecta, a confirmação de B é barrada."""
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    _, head_2 = _empty_org(factory)
    preview = client.post(PREVIEW, json=_token_body(), headers=head_2)
    assert preview.status_code == 200  # ainda ninguém reservou a usina: a prévia passa
    created = _preview_confirm(client, head_1, _token_body())
    assert created.status_code == 201
    data = preview.json()
    plant = {k: v for k, v in data["plant"].items() if k != "city"}

    response = client.post(
        CONFIRM, json={"ticket": data["ticket"], "plant": plant}, headers=head_2
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "provider_inverter_in_another_plant"


# --- o que a coleta faz com as duas conexões gravadas ----------------------


class _SamePlantProvider(SolarProvider):
    """O token das duas organizações enxerga a mesma usina física."""

    async def list_devices(self) -> list[SolarDevice]:
        return [SolarDevice(SERIAL, "Usina Growatt", None, None)]

    async def get_overview(self, serial_number: str) -> DeviceOverview:  # pragma: no cover
        raise NotImplementedError

    async def get_daily_energy(self, serial_number, start, end, *, expect_complete=False):
        return [ProviderDailyEnergy(date(2026, 11, 1), Decimal("10.5"))]


def _connect_both(client, admins, factory) -> None:
    """Duplicata legada gravada direto: duas conexões e nenhuma reserva.

    É o que pode existir em produção de antes das reservas (ADR-100); a rota nova
    já não deixa criar isso.
    """

    async def _seed() -> None:
        async with factory() as session:
            for plant_id, fingerprint in ((PLANT_A, "fp-a"), (PLANT_B, "fp-b")):
                session.add(
                    ProviderAccountRecord(
                        plant_id=plant_id,
                        provider=GROWATT_TOKEN,
                        login_hint="to***",
                        account_fingerprint=fingerprint,
                        ciphertext=b"x",
                        key_version=1,
                        active=True,
                    )
                )
            await session.commit()

    asyncio.run(_seed())
    assert asyncio.run(_claims(factory)) == []


def test_daily_collection_first_plant_owns_the_device_and_second_fails_closed(env) -> None:
    """Com as duas conexões gravadas (lacuna), quem coleta primeiro fica com o Device.

    A outra organização recebe ``CollectionPlantError`` na coleta diária (job.py:
    erro não-``ProviderError`` => a usina falha no job, sem dado e sem fila de nova
    tentativa). Nada da produção de A é gravado em B.
    """
    client, factory, admins, _ = env
    _connect_both(client, admins, factory)

    async def _collect(plant_id):
        async with factory() as session:
            return await SolarCollectionService(
                session,
                _SamePlantProvider(),
                provider_name=GROWATT_TOKEN,
                energy_source="GROWATT_TOKEN",
            ).collect(plant_id=plant_id, start=date(2026, 11, 1), end=date(2026, 11, 1))

    first = asyncio.run(_collect(PLANT_B))  # a ordem do job é por nome da usina; aqui B vence
    assert first.records_received == 1
    with pytest.raises(CollectionPlantError):
        asyncio.run(_collect(PLANT_A))

    devices = asyncio.run(_devices(factory))
    assert [(d.plant_id, d.serial_number) for d in devices] == [(PLANT_B, SERIAL)]

    async def _energy_rows() -> int:
        async with factory() as session:
            return len(list(await session.scalars(select(DailyEnergy))))

    assert asyncio.run(_energy_rows()) == 1


def test_meter_reading_job_creates_the_device_and_fails_the_other_org(env) -> None:
    """Leitura da madrugada (``record_meter_totals``): mesmo desfecho do job diário."""
    client, factory, admins, _ = env
    _connect_both(client, admins, factory)

    async def _meter(plant_id):
        async with factory() as session:
            service = SolarCollectionService(
                session,
                _SamePlantProvider(),
                provider_name=GROWATT_TOKEN,
                energy_source="METER",
            )
            try:
                return await service.record_meter_totals(
                    plant_id=plant_id,
                    totals={SERIAL: Decimal("1000")},
                    covered_date=date(2026, 11, 10),
                )
            finally:
                await session.commit()

    asyncio.run(_meter(PLANT_A))
    with pytest.raises(CollectionPlantError):
        asyncio.run(_meter(PLANT_B))

    assert [(d.plant_id, d.provider) for d in asyncio.run(_devices(factory))] == [
        (PLANT_A, GROWATT_TOKEN)
    ]

    async def _readings() -> list[MeterReading]:
        async with factory() as session:
            return list(await session.scalars(select(MeterReading)))

    assert [r.plant_id for r in asyncio.run(_readings())] == [PLANT_A]


# --- corrida: a restrição UNIQUE é a barreira real --------------------------


@pytest.fixture
def blind_early_check(monkeypatch):
    """A conferência antecipada não vê nada: só o UNIQUE do banco barra a segunda."""

    async def _never(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(provider_router, "_inverter_in_another_plant", _never)


async def _refusals(factory, resource_id) -> list[AuditEventRecord]:
    async with factory() as session:
        return list(
            await session.scalars(
                select(AuditEventRecord).where(
                    AuditEventRecord.action == "provider_account.verify_failed",
                    AuditEventRecord.resource_id == str(resource_id),
                )
            )
        )


async def _plants_of(factory, org_id) -> list[Plant]:
    async with factory() as session:
        return list(await session.scalars(select(Plant).where(Plant.organization_id == org_id)))


def test_race_put_unique_refuses_b_and_audits_the_refusal(env, blind_early_check) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200

    response = _put(client, URL_B, _token_body(), admins["b"])

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}
    assert [r.plant_id for r in asyncio.run(_records(factory))] == [PLANT_A]
    refusals = asyncio.run(_refusals(factory, PLANT_B))
    assert [r.details for r in refusals] == [
        {"provider": GROWATT_TOKEN, "reason": "provider_inverter_in_another_plant"}
    ]


def test_race_connect_unique_refuses_b_without_leaving_a_plant(env, blind_early_check) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    org_2, head_2 = _empty_org(factory)
    assert client.post(CONNECT, json=_token_body(), headers=head_1).status_code == 201

    response = client.post(CONNECT, json=_token_body(), headers=head_2)

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}
    assert asyncio.run(_plants_of(factory, org_2)) == []
    assert [r.details for r in asyncio.run(_refusals(factory, org_2))] == [
        {"provider": GROWATT_TOKEN, "reason": "provider_inverter_in_another_plant"}
    ]


def test_race_confirm_unique_refuses_b_without_leaving_a_plant(env, blind_early_check) -> None:
    client, factory, _admins, _ = env
    _, head_1 = _empty_org(factory)
    org_2, head_2 = _empty_org(factory)
    assert _preview_confirm(client, head_1, _token_body()).status_code == 201

    response = _preview_confirm(client, head_2, _token_body())

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}
    assert asyncio.run(_plants_of(factory, org_2)) == []
    assert [r.details for r in asyncio.run(_refusals(factory, org_2))] == [
        {"provider": GROWATT_TOKEN, "reason": "provider_inverter_in_another_plant"}
    ]


# --- ciclo de vida das reservas --------------------------------------------


def test_disconnect_before_collection_releases_the_claims_for_b(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200
    assert _put(client, URL_B, _token_body(), admins["b"]).status_code == 409

    assert client.delete(URL_A, headers=admins["a"]).status_code == 204

    assert asyncio.run(_claims(factory)) == []
    assert _put(client, URL_B, _token_body(), admins["b"]).status_code == 200
    assert [c.plant_id for c in asyncio.run(_claims(factory))] == [PLANT_B]


def test_reconnect_with_other_serials_replaces_the_claims(env) -> None:
    client, factory, admins, verifier = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200
    verifier.serials = ["GW-PLANT-OUTRA"]
    assert _put(client, URL_A, _password_body(), admins["a"]).status_code == 200

    assert [c.serial_number for c in asyncio.run(_claims(factory))] == ["GW-PLANT-OUTRA"]
    verifier.serials = [SERIAL]
    assert _put(client, URL_B, _token_body(), admins["b"]).status_code == 200  # SERIAL liberado
    verifier.serials = ["GW-PLANT-OUTRA"]
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200  # A mantém a sua


def test_disconnect_after_collection_keeps_blocking_through_the_device(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200
    _seed_device(factory, PLANT_A, GROWATT_TOKEN)
    assert client.delete(URL_A, headers=admins["a"]).status_code == 204
    assert asyncio.run(_claims(factory)) == []

    response = _put(client, URL_B, _token_body(), admins["b"])

    assert response.status_code == 409
    assert response.json() == {"detail": "provider_inverter_in_another_plant"}


def test_token_with_several_plants_claims_all_of_them(env) -> None:
    client, factory, admins, verifier = env
    verifier.serials = [SERIAL, "GW-PLANT-2", SERIAL]

    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200

    assert sorted(c.serial_number for c in asyncio.run(_claims(factory))) == [
        SERIAL,
        "GW-PLANT-2",
    ]
    verifier.serials = ["GW-PLANT-2"]
    assert _put(client, URL_B, _token_body(), admins["b"]).status_code == 409


def test_other_brand_with_the_same_serial_is_not_blocked_by_a_growatt_claim(env) -> None:
    client, factory, admins, _ = env
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200

    other = {"provider": "NEPVIEWER", "login": "cliente@example.com", "password": "s3nh4"}
    assert _put(client, URL_B, other, admins["b"]).status_code == 200

    families = {(c.plant_id, c.provider_family) for c in asyncio.run(_claims(factory))}
    assert families == {(PLANT_A, "GROWATT"), (PLANT_B, "NEPVIEWER")}


# --- nada do outro cliente nem do erro do banco sai na recusa ---------------


@pytest.mark.parametrize("early_check", [True, False])
def test_refusal_leaks_nothing_about_a_or_the_database_error(
    env, monkeypatch, early_check
) -> None:
    client, factory, admins, _ = env
    if not early_check:

        async def _never(*_args, **_kwargs) -> bool:
            return False

        monkeypatch.setattr(provider_router, "_inverter_in_another_plant", _never)
    assert _put(client, URL_A, _token_body(), admins["a"]).status_code == 200

    response = _put(client, URL_B, _token_body(), admins["b"])

    assert response.status_code == 409
    audits = asyncio.run(_refusals(factory, PLANT_B))
    assert len(audits) == 1
    visible = response.text + json.dumps(audits[0].details)
    for forbidden in (
        str(PLANT_A),
        "Casa A",
        SERIAL,
        "uq_provider_plant_claims",
        "UNIQUE",
        "IntegrityError",
        "provider_plant_claims",
    ):
        assert forbidden not in visible
