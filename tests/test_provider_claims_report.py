from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from mplacas.audit import db_models as _audit_models  # noqa: F401
from mplacas.audit.db_models import AuditEventRecord
from mplacas.cloud_jobs import _build_parser
from mplacas.db import models as _models  # noqa: F401
from mplacas.db.base import Base
from mplacas.db.models import Device, Plant
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN, NEPVIEWER
from mplacas.providers.claims_report import (
    R1,
    R2,
    R3,
    R4,
    ClaimsReport,
    build_claims_report,
    render_claims_report,
)
from mplacas.providers.db_models import ProviderAccountRecord

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
PLANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
SECRET_LOGIN = "login-secreto-xyz@example.com"
_ENGINES: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    while _ENGINES:
        await _ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                OrganizationRecord(id=ORG_A, name="A", slug="a", active=True),
                OrganizationRecord(id=ORG_B, name="B", slug="b", active=True),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Plant(id=PLANT_A, organization_id=ORG_A, name="A"),
                Plant(id=PLANT_B, organization_id=ORG_B, name="B"),
            ]
        )
        await session.commit()
    return factory


def _account(plant_id, provider=GROWATT, *, age_hours=100, active=True, **extra):
    created = NOW - timedelta(hours=age_hours)
    return ProviderAccountRecord(
        plant_id=plant_id,
        provider=provider,
        login_hint=SECRET_LOGIN,
        account_fingerprint=f"fp-{uuid.uuid4().hex}" if active else None,
        ciphertext=b"cifrado-secreto" if active else None,
        key_version=1 if active else None,
        active=active,
        created_at=created,
        **extra,
    )


def _device(plant_id, provider, serial):
    return Device(plant_id=plant_id, provider=provider, serial_number=serial)


async def _report(factory, **kwargs) -> ClaimsReport:
    async with factory() as session:
        return await build_claims_report(session, now=lambda: NOW, **kwargs)


async def _seed(factory, *rows) -> None:
    async with factory() as session:
        session.add_all(rows)
        await session.commit()


def _rule(report: ClaimsReport, rule: str):
    return [f for f in report.findings if f.rule == rule]


async def test_r1_mesmo_serial_em_dois_tipos_e_duas_usinas_e_reportado() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
        _device(PLANT_B, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    found = _rule(await _report(factory), R1)
    assert {f.plant_id for f in found} == {PLANT_A, PLANT_B}
    assert all(f.serials == ("GW-PLANT-1",) for f in found)


async def test_r1_mesmo_serial_na_mesma_usina_nao_e_r1_mas_r4() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    report = await _report(factory)
    assert _rule(report, R1) == []
    assert [f.plant_id for f in _rule(report, R4)] == [PLANT_A]


async def test_r1_serial_diferente_ou_fora_da_familia_nao_e_reportado() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
        _device(PLANT_B, GROWATT_TOKEN, "GW-PLANT-2"),
        _device(PLANT_B, NEPVIEWER, "GW-PLANT-1"),
    )
    assert _rule(await _report(factory), R1) == []


async def test_r2_conexao_ativa_com_collection_plant_error_e_reportada() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, last_failure_code="CollectionPlantError"),
        _account(PLANT_B, GROWATT_TOKEN, last_failure_code="ProviderDeferred"),
        AuditEventRecord(
            action="provider_account.history_import_failed",
            resource_type="plant",
            resource_id=str(PLANT_A),
            outcome="FAILED",
            actor_role="ADMIN",
            actor_credential_id="x",
            details={"provider": GROWATT, "reason": "provider_inverter_in_another_plant"},
        ),
    )
    found = _rule(await _report(factory), R2)
    assert [f.plant_id for f in found] == [PLANT_A]
    assert found[0].last_failure_code == "CollectionPlantError"
    assert found[0].refusals_audited == 1


async def test_r2_conexao_inativa_nao_e_reportada() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, active=False, last_failure_code="CollectionPlantError"),
    )
    assert _rule(await _report(factory), R2) == []


async def test_r3_49h_sem_aparelho_reportada_e_47h_nao() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, age_hours=49),
        _account(PLANT_B, GROWATT_TOKEN, age_hours=47),
    )
    found = _rule(await _report(factory), R3)
    assert [f.plant_id for f in found] == [PLANT_A]
    assert found[0].organization_id == ORG_A


async def test_r3_usa_rotated_at_como_conexao_mais_recente() -> None:
    factory = await _factory()
    await _seed(factory, _account(PLANT_A, age_hours=500, rotated_at=NOW - timedelta(hours=1)))
    assert _rule(await _report(factory), R3) == []


async def test_r3_inativa_ou_com_aparelho_nao_e_reportada_e_limite_e_parametro() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, active=False, age_hours=100),
        _account(PLANT_B, age_hours=100),
        _device(PLANT_B, GROWATT_TOKEN, "GW-PLANT-9"),
    )
    assert _rule(await _report(factory), R3) == []


async def test_r3_limite_configuravel() -> None:
    factory = await _factory()
    await _seed(factory, _account(PLANT_A, age_hours=10))
    assert _rule(await _report(factory), R3) == []
    assert len(_rule(await _report(factory, suspect_after=timedelta(hours=5)), R3)) == 1


async def test_r4_mais_de_um_aparelho_na_usina_e_reportado_e_um_so_nao() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
        _device(PLANT_A, GROWATT, "GW-PLANT-2"),
        _device(PLANT_B, GROWATT, "GW-PLANT-3"),
    )
    found = _rule(await _report(factory), R4)
    assert [f.plant_id for f in found] == [PLANT_A]
    assert found[0].serials == ("GW-PLANT-1", "GW-PLANT-2")


async def test_base_limpa_nao_tem_achados() -> None:
    factory = await _factory()
    report = await _report(factory)
    assert report.findings == ()
    assert "Total por regra: R1=0, R2=0, R3=0, R4=0" in render_claims_report(report)


async def test_relatorio_nao_grava_nada() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, last_failure_code="CollectionPlantError"),
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
        _device(PLANT_B, GROWATT_TOKEN, "GW-PLANT-1"),
    )

    async def counts() -> dict[str, int]:
        async with factory() as session:
            return {
                name: int(
                    await session.scalar(select(func.count()).select_from(table)) or 0
                )
                for name, table in Base.metadata.tables.items()
            }

    before = await counts()
    report = await _report(factory)
    assert report.findings
    assert await counts() == before


async def test_saida_nao_contem_login_nem_segredos() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, last_failure_code="CollectionPlantError"),
        _account(PLANT_B, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
    )
    text = render_claims_report(await _report(factory))
    assert "R2" in text and "R3" in text
    assert SECRET_LOGIN not in text
    assert "login-secreto" not in text
    assert "cifrado" not in text
    assert "fp-" not in text


def test_subcomando_registrado_no_parser() -> None:
    args = _build_parser().parse_args(["provider-claims-report"])
    assert args.command == "provider-claims-report"


async def test_somente_totais_nao_mostra_usina_organizacao_nem_serial() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, last_failure_code="CollectionPlantError"),
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
    )
    text = render_claims_report(await _report(factory), totals_only=True)
    assert "Total por regra: R1=0, R2=1" in text
    assert str(PLANT_A) not in text
    assert "GW-PLANT-1" not in text
    assert "organizacao=" not in text


def test_subcomando_aceita_somente_totais() -> None:
    args = _build_parser().parse_args(["provider-claims-report", "--totals-only"])
    assert args.totals_only is True
