"""Growatt descontinuada (ADR-101): nenhuma conexão nova; NEPViewer segue igual."""

from __future__ import annotations

import asyncio
import base64
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
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import (
    CONNECTABLE_PROVIDERS,
    DISCONTINUED_PROVIDERS,
    GROWATT,
    GROWATT_TOKEN,
    NEPVIEWER,
    SUPPORTED_PROVIDERS,
    ProviderAccountService,
    ProviderLogin,
)
from mplacas.providers.connect_ticket import issue_ticket
from mplacas.providers.db_models import ProviderAccountRecord
from mplacas.providers.router import ProviderInspection

KEY = base64.b64encode(b"\x09" * KEY_BYTES).decode()
PLANT = uuid.UUID("00000000-0000-0000-0000-0000000000f1")
URL = f"/plants/{PLANT}/provider-account"
SENHA = "s3nh4-do-inversor-xyz"
TOKEN = "token.da.usina.xyz"


def _corpo(provider: str) -> dict[str, str]:
    if provider == GROWATT_TOKEN:
        return {"provider": provider, "password": TOKEN}
    return {"provider": provider, "login": "rogerio", "password": SENHA}


async def _preparar():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    org = uuid.uuid4()
    async with factory() as session:
        session.add(OrganizationRecord(id=org, name="A", slug=f"a-{org.hex[:8]}", active=True))
        await session.flush()
        session.add(Plant(id=PLANT, organization_id=org, name="Casa"))
        await session.commit()
    return factory, engine, org


class _Chamadas:
    """Tudo que sairia para a marca: precisa ficar vazio nas recusas."""

    def __init__(self) -> None:
        self.verificacoes: list[str] = []
        self.clientes: list[str] = []

    async def verificar(self, provider: str, credentials: ProviderLogin) -> ProviderInspection:
        self.verificacoes.append(provider)
        return ProviderInspection(["SN-1"], None)

    def construir(self, provider: str, **_kwargs):
        self.clientes.append(provider)
        raise AssertionError("a marca não pode ser chamada")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv("MPLACAS_PROVIDER_SECRET_KEYS", f"1:{KEY}")
    get_settings.cache_clear()
    factory, engine, org = asyncio.run(_preparar())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(provider_router, "SessionFactory", factory)
    chamadas = _Chamadas()
    monkeypatch.setattr(provider_router, "verify_provider_account", chamadas.verificar)
    monkeypatch.setattr(provider_router, "build_client", chamadas.construir)
    holder = uuid.uuid4()
    admin = {
        "Authorization": "Bearer "
        + encode_access_token(holder, org, OperationsRole.ADMIN.value)
    }
    with TestClient(app) as client:
        yield client, factory, org, admin, holder, chamadas
    asyncio.run(engine.dispose())
    get_settings.cache_clear()


async def _registros(factory) -> list[ProviderAccountRecord]:
    async with factory() as session:
        return list(await session.scalars(select(ProviderAccountRecord)))


async def _auditoria(factory) -> list[AuditEventRecord]:
    async with factory() as session:
        return list(await session.scalars(select(AuditEventRecord)))


def _semear_conexao(factory, provider: str) -> None:
    """Conexão que já existia antes da descontinuação (gravada direto no banco)."""

    async def _run() -> None:
        async with factory() as session:
            login = ProviderLogin(login="rogerio", password=SENHA)
            box = SecretBox.from_keyring(f"1:{KEY}")
            await ProviderAccountService(session, box).save(
                plant_id=PLANT, provider=provider, credentials=login, serials=["SN-1"]
            )
            await session.commit()

    asyncio.run(_run())


def test_conjuntos_de_marcas_do_adr_101() -> None:
    assert CONNECTABLE_PROVIDERS == {NEPVIEWER}
    assert DISCONTINUED_PROVIDERS == {GROWATT, GROWATT_TOKEN}
    # A coleta das conexões existentes continua lendo as três marcas.
    assert SUPPORTED_PROVIDERS == {NEPVIEWER, GROWATT, GROWATT_TOKEN}


@pytest.mark.parametrize("provider", [GROWATT, GROWATT_TOKEN])
def test_put_growatt_e_recusado_sem_gravar_nem_chamar_a_marca(env, provider) -> None:
    client, factory, _org, admin, _holder, chamadas = env

    resposta = client.put(URL, json=_corpo(provider), headers=admin)

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "provider_unsupported"}
    assert SENHA not in resposta.text and TOKEN not in resposta.text
    assert asyncio.run(_registros(factory)) == []  # nenhum ciphertext gravado
    assert [e.action for e in asyncio.run(_auditoria(factory))] == []  # nem "saved"
    assert chamadas.verificacoes == [] and chamadas.clientes == []


@pytest.mark.parametrize("provider", [GROWATT, GROWATT_TOKEN])
@pytest.mark.parametrize("rota", ["/plants/connect", "/plants/connect/preview"])
def test_primeira_conexao_e_previa_growatt_sao_recusadas(env, provider, rota) -> None:
    client, factory, _org, admin, _holder, chamadas = env

    resposta = client.post(rota, json=_corpo(provider), headers=admin)

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "provider_unsupported"}
    assert asyncio.run(_registros(factory)) == []
    assert chamadas.verificacoes == [] and chamadas.clientes == []
    assert "provider_account.saved" not in [e.action for e in asyncio.run(_auditoria(factory))]


@pytest.mark.parametrize("provider", [GROWATT, GROWATT_TOKEN])
def test_bilhete_growatt_emitido_antes_e_recusado_na_confirmacao(env, provider) -> None:
    client, factory, org, admin, holder, chamadas = env
    # Usina nova: organização sem usina, como no assistente de primeira conexão.
    nova = uuid.uuid4()

    async def _org_vazia() -> None:
        async with factory() as session:
            slug = f"n-{nova.hex[:8]}"
            session.add(OrganizationRecord(id=nova, name="N", slug=slug, active=True))
            await session.commit()

    asyncio.run(_org_vazia())
    cabecalho = {
        "Authorization": "Bearer " + encode_access_token(holder, nova, OperationsRole.ADMIN.value)
    }
    bilhete, _ = issue_ticket(
        SecretBox.from_keyring(f"1:{KEY}"),
        organization_id=nova,
        holder=f"user:{holder}",
        provider=provider,
        credentials=ProviderLogin(login="rogerio", password=SENHA),
        serials=["SN-1"],
        draft={},
        origins={},
    )

    resposta = client.post(
        "/plants/connect/confirm",
        json={"ticket": bilhete, "plant": {"name": "Casa"}},
        headers=cabecalho,
    )

    assert resposta.status_code == 422, resposta.text
    assert resposta.json() == {"detail": "provider_unsupported"}
    assert asyncio.run(_registros(factory)) == []
    assert chamadas.verificacoes == [] and chamadas.clientes == []


@pytest.mark.parametrize("provider", [GROWATT, GROWATT_TOKEN])
@pytest.mark.parametrize("rota", ["import-history", "refresh-profile"])
def test_conexao_growatt_existente_nao_importa_nem_relê_cadastro(env, provider, rota) -> None:
    client, factory, _org, admin, _holder, chamadas = env
    _semear_conexao(factory, provider)

    resposta = client.post(f"{URL}/{rota}", headers=admin)

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "provider_discontinued"}
    assert chamadas.clientes == []  # a marca não foi chamada
    registro = asyncio.run(_registros(factory))[0]
    assert registro.active and registro.ciphertext  # nada foi desativado nem apagado


def test_nepviewer_continua_conectando_e_previa_funciona(env) -> None:
    client, factory, _org, admin, _holder, chamadas = env

    resposta = client.put(URL, json=_corpo(NEPVIEWER), headers=admin)

    assert resposta.status_code == 200
    assert resposta.json()["provider"] == NEPVIEWER
    assert chamadas.verificacoes == [NEPVIEWER]
    assert [e.action for e in asyncio.run(_auditoria(factory))] == ["provider_account.saved"]
    assert asyncio.run(_registros(factory))[0].provider == NEPVIEWER
