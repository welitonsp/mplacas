"""Troca de conexão Growatt (senha <-> token) não pode dobrar a produção da usina.

A mesma usina física tem o mesmo número de série ``GW-PLANT-<id>`` nas duas
marcas (``GROWATT`` e ``GROWATT_TOKEN``), mas ``devices`` é único por
``(provider, serial_number)`` e ``SolarCollectionService._get_or_create_device``
procura o aparelho só pelo ``provider`` da conexão atual. Estes testes fixam a
expectativa CORRETA (um aparelho por usina física na usina; o total do dia é a
produção de um só). Enquanto a falha existe, os que a provam ficam como
``xfail(strict=True)``: quando for corrigida, a suíte avisa.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.providers.router as provider_router
from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.secret_box import KEY_BYTES
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy as DailyEnergyRow
from mplacas.db.models import Device, Plant
from mplacas.intelligence.cycle_service import analyze_persisted_cycle
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN
from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    SolarDevice,
    SolarProvider,
)
from mplacas.providers.claims_report import R4, build_claims_report
from mplacas.providers.db_models import ProviderAccountRecord
from mplacas.providers.factory import ENERGY_SOURCES
from mplacas.providers.router import ProviderInspection
from mplacas.services.collection import SolarCollectionService

KEY = base64.b64encode(b"\x0b" * KEY_BYTES).decode()
PLANT = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
SERIAL = "GW-PLANT-4242"
URL = f"/plants/{PLANT}/provider-account"
HISTORY = f"{URL}/import-history"
METER_SOURCE = "GROWATT_TOTAL_DIFF"
KWH_POR_DIA = Decimal("10.000")
DIAS = 3

XFAIL_DUPLICA = "troca de conexão cria 2º aparelho p/ o mesmo GW-PLANT e dobra a produção"


def _ontem() -> date:
    # Mesma conta da importação de histórico (provider_router.import_production_history).
    return datetime.now(ZoneInfo(get_settings().timezone)).date() - timedelta(days=1)


def _dias(quantos: int = DIAS) -> list[date]:
    fim = _ontem()
    return [fim - timedelta(days=n) for n in range(quantos - 1, -1, -1)]


class FakeGrowatt(SolarProvider):
    """Cliente que devolve a mesma usina física (mesmo serial) e os mesmos dias."""

    def __init__(self, dias: list[date], kwh: Decimal = KWH_POR_DIA) -> None:
        self._dias = dias
        self._kwh = kwh

    async def list_devices(self) -> list[SolarDevice]:
        return [SolarDevice(serial_number=SERIAL, model_name="Usina Growatt", city=None,
                            last_update=None)]

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        raise NotImplementedError

    async def get_daily_energy(
        self, serial_number: str, start: date, end: date, *, expect_complete: bool = False
    ) -> list[DailyEnergy]:
        return [
            DailyEnergy(production_date=d, energy_kwh=self._kwh)
            for d in self._dias
            if start <= d <= end
        ]

    async def aclose(self) -> None:
        return None


async def _setup():
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


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv("MPLACAS_PROVIDER_SECRET_KEYS", f"1:{KEY}")
    get_settings.cache_clear()
    factory, engine, org = asyncio.run(_setup())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(provider_router, "SessionFactory", factory)

    async def _verifier(provider, credentials):
        return ProviderInspection([SERIAL], None)  # as duas marcas veem a mesma usina

    monkeypatch.setattr(provider_router, "verify_provider_account", _verifier)
    monkeypatch.setattr(
        provider_router, "build_client", lambda *a, **k: FakeGrowatt(_dias())
    )
    admin = encode_access_token(uuid.uuid4(), org, OperationsRole.ADMIN.value)
    with TestClient(app) as client:
        yield client, factory, {"Authorization": f"Bearer {admin}"}
    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _conectar(client, headers, provider: str) -> None:
    body = (
        {"provider": GROWATT_TOKEN, "password": "token-abc123"}
        if provider == GROWATT_TOKEN
        else {"provider": GROWATT, "login": "cliente@example.com", "password": "s3nh4"}
    )
    assert client.put(URL, json=body, headers=headers).status_code == 200


def _importar(client, headers) -> None:
    response = client.post(HISTORY, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["history_available"] is True
    provider_router._LIVE_CACHE.clear()


def _trocar_senha_por_token(client, headers) -> None:
    """Senha + 90 dias; depois o mesmo caminho que o produto incentiva: token + 90 dias."""
    _conectar(client, headers, GROWATT)
    _importar(client, headers)
    _conectar(client, headers, GROWATT_TOKEN)
    _importar(client, headers)


async def _aparelhos(factory) -> list[tuple[str, str]]:
    async with factory() as session:
        rows = await session.execute(
            select(Device.provider, Device.serial_number).where(Device.plant_id == PLANT)
        )
        return sorted(rows.all())


async def _total_por_dia(factory) -> dict[date, Decimal]:
    """Soma por usina e dia, como os leitores do painel (SUM sobre todos os aparelhos)."""
    async with factory() as session:
        rows = await session.execute(
            select(DailyEnergyRow.production_date, func.sum(DailyEnergyRow.energy_kwh))
            .join(Device, DailyEnergyRow.device_id == Device.id)
            .where(Device.plant_id == PLANT)
            .group_by(DailyEnergyRow.production_date)
        )
        return {day: Decimal(total) for day, total in rows.all()}


# --- 1. Rota real: senha -> token ---------------------------------------------


def test_controle_reimportar_na_mesma_marca_nao_duplica(env) -> None:
    """Controle: com a MESMA marca o aparelho é reaproveitado (idempotente)."""
    client, factory, headers = env
    _conectar(client, headers, GROWATT_TOKEN)
    _importar(client, headers)
    _importar(client, headers)

    assert asyncio.run(_aparelhos(factory)) == [(GROWATT_TOKEN, SERIAL)]
    assert set(asyncio.run(_total_por_dia(factory)).values()) == {KWH_POR_DIA}


@pytest.mark.xfail(strict=True, reason=XFAIL_DUPLICA)
def test_apos_trocar_senha_por_token_nao_ha_segundo_aparelho(env) -> None:
    client, factory, headers = env
    _trocar_senha_por_token(client, headers)

    aparelhos = asyncio.run(_aparelhos(factory))
    assert len({serial for _, serial in aparelhos}) == len(aparelhos), aparelhos


@pytest.mark.xfail(strict=True, reason=XFAIL_DUPLICA)
def test_total_do_dia_apos_a_troca_e_a_producao_de_um_so(env) -> None:
    client, factory, headers = env
    _trocar_senha_por_token(client, headers)

    totais = asyncio.run(_total_por_dia(factory))
    assert totais == {dia: KWH_POR_DIA for dia in _dias()}


@pytest.mark.xfail(strict=True, reason=XFAIL_DUPLICA)
def test_producao_do_ciclo_da_fatura_apos_a_troca_nao_dobra(env) -> None:
    """O que o cliente vê: produção no período da fatura (conferência com a distribuidora)."""
    client, factory, headers = env
    _trocar_senha_por_token(client, headers)
    dias = _dias()

    async def _producao_do_ciclo() -> Decimal:
        async with factory() as session:
            bill = UtilityBillRecord(
                plant_id=PLANT,
                distributor="EQUATORIAL_GO",
                reference_month=dias[-1].strftime("%Y-%m"),
                cycle_start=dias[0],
                cycle_end=dias[-1],
                billed_days=len(dias),
                imported_kwh=Decimal("8"),
                injected_kwh=Decimal("12"),
                compensated_kwh=Decimal("8"),
                credit_balance_kwh=Decimal("20"),
                total_amount_brl=Decimal("50"),
                public_lighting_brl=Decimal("30"),
                status=BillStatus.CONFIRMED,
                source_hash="d" * 64,
            )
            session.add(bill)
            await session.commit()
            result = await analyze_persisted_cycle(
                session, bill_id=bill.id, plant_id=PLANT, expected_production_kwh=Decimal("30")
            )
            return result.intelligence.reconciliation.cycle_production_kwh

    assert asyncio.run(_producao_do_ciclo()) == KWH_POR_DIA * DIAS


# --- 2. Serviço direto: sentido inverso (token -> senha) e leitura do total ---


async def _banco_so():
    factory, engine, _org = await _setup()
    return factory, engine


async def _coletar(factory, provider: str, dias: list[date], kwh: Decimal = KWH_POR_DIA) -> None:
    async with factory() as session:
        await SolarCollectionService(
            session,
            FakeGrowatt(dias, kwh),
            provider_name=provider,
            energy_source=ENERGY_SOURCES[provider],
        ).collect(plant_id=PLANT, start=min(dias), end=max(dias), consolidate_through=max(dias))


@pytest.mark.xfail(strict=True, reason=XFAIL_DUPLICA)
@pytest.mark.asyncio
async def test_sentido_inverso_token_depois_senha_nao_duplica() -> None:
    factory, engine = await _banco_so()
    try:
        dias = _dias()
        await _coletar(factory, GROWATT_TOKEN, dias)
        await _coletar(factory, GROWATT, dias)

        aparelhos = await _aparelhos(factory)
        assert len({serial for _, serial in aparelhos}) == len(aparelhos), aparelhos
        assert await _total_por_dia(factory) == {dia: KWH_POR_DIA for dia in dias}
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason=XFAIL_DUPLICA)
@pytest.mark.asyncio
async def test_valores_diferentes_entre_as_fontes_nao_somam() -> None:
    """GROWATT_CLASSIC e GROWATT_OPENAPI_V1 medem o mesmo dia com precisão diferente."""
    factory, engine = await _banco_so()
    try:
        dias = _dias()
        await _coletar(factory, GROWATT, dias, Decimal("10.000"))
        await _coletar(factory, GROWATT_TOKEN, dias, Decimal("10.400"))

        totais = await _total_por_dia(factory)
        assert all(total <= Decimal("10.400") for total in totais.values()), totais
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason=XFAIL_DUPLICA)
@pytest.mark.asyncio
async def test_leitura_do_total_da_madrugada_nao_duplica_dia_ja_coletado() -> None:
    """Caminho noturno (ADR-098, ``GROWATT_TOTAL_DIFF``) depois da troca para token."""
    factory, engine = await _banco_so()
    try:
        dias = _dias()
        await _coletar(factory, GROWATT, dias)  # histórico pela senha (GROWATT_CLASSIC)
        vespera, hoje = dias[-2], dias[-1]
        async with factory() as session:
            service = SolarCollectionService(
                session, FakeGrowatt(dias), provider_name=GROWATT_TOKEN, energy_source=METER_SOURCE
            )
            await service.record_meter_totals(
                plant_id=PLANT, totals={SERIAL: Decimal("1000")}, covered_date=vespera
            )
            await service.record_meter_totals(
                plant_id=PLANT, totals={SERIAL: Decimal("1010")}, covered_date=hoje
            )
            await session.commit()

        totais = await _total_por_dia(factory)
        assert totais[hoje] == KWH_POR_DIA, totais
        assert len({s for _, s in await _aparelhos(factory)}) == len(await _aparelhos(factory))
    finally:
        await engine.dispose()


# --- 3. Detecção: a regra R4 do relatório de reservas enxerga a duplicata ------


@pytest.mark.asyncio
async def test_r4_do_relatorio_de_reservas_aponta_a_usina_com_dois_aparelhos() -> None:
    factory, engine = await _banco_so()
    try:
        async with factory() as session:
            session.add_all(
                [
                    Device(plant_id=PLANT, provider=GROWATT, serial_number=SERIAL),
                    Device(plant_id=PLANT, provider=GROWATT_TOKEN, serial_number=SERIAL),
                    ProviderAccountRecord(
                        plant_id=PLANT,
                        provider=GROWATT_TOKEN,
                        login_hint="to***3f",
                        account_fingerprint="fp-teste",
                        ciphertext=b"cifrado",
                        key_version=1,
                        active=True,
                    ),
                ]
            )
            await session.commit()
        async with factory() as session:
            report = await build_claims_report(session, now=lambda: datetime.now(UTC))

        r4 = [f for f in report.findings if f.rule == R4]
        assert [f.plant_id for f in r4] == [PLANT]
        assert r4[0].serials == (SERIAL, SERIAL)
    finally:
        await engine.dispose()


def test_modelo_nao_impede_o_mesmo_serial_em_duas_marcas_na_mesma_usina() -> None:
    """Documenta o buraco: a UNIQUE é (provider, serial), então o banco aceita as duas linhas."""
    uniques = {
        tuple(c.name for c in constraint.columns)
        for constraint in Device.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("provider", "serial_number") in uniques
    assert not any("plant_id" in cols for cols in uniques)
