"""Exclusão definitiva das usinas Growatt (ADR-101): simulação, aplicação, recusas, sigilo."""

from __future__ import annotations

import datetime as dt
import enum
import re
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import mplacas.cloud_jobs as cloud_jobs
from mplacas.alerts import db_models as _alerts  # noqa: F401
from mplacas.audit.db_models import AuditEventRecord
from mplacas.billing import db_models as _billing  # noqa: F401
from mplacas.climate import db_models as _climate  # noqa: F401
from mplacas.cloud_jobs import OperatorError, _build_parser, run_purge_discontinued_plants
from mplacas.collection import db_models as _collection  # noqa: F401
from mplacas.credentials.db_models import ApiCredentialRecord, OperationalUserRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DailyEnergyVersion, Device, MeterReading, Plant
from mplacas.events import db_models as _events  # noqa: F401
from mplacas.operations import models as _operations  # noqa: F401
from mplacas.orchestration import db_models as _orchestration  # noqa: F401
from mplacas.organizations import invitation_db_models as _invitations  # noqa: F401
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.photovoltaic import db_models as _pv  # noqa: F401
from mplacas.providers.db_models import ProviderAccountRecord, ProviderPlantClaimRecord
from mplacas.providers.purge_discontinued import CATEGORIES, PRESERVED_TABLES, AUDIT_ACTION
from mplacas.reports import db_models as _reports  # noqa: F401
from mplacas.alerts.db_models import AlertDeliveryRecord
from mplacas.billing.db_models import UtilityBillRecord
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.collection.db_models import CollectionTaskRecord
from mplacas.events.db_models import OutboxEventRecord
from mplacas.orchestration.db_models import PipelineExecutionRecord
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.reports.db_models import MonthlyReportSnapshotRecord, ReportExportTask

ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
GW = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
NEP_A = uuid.UUID("00000000-0000-0000-0000-0000000000c2")
NEP_B = uuid.UUID("00000000-0000-0000-0000-0000000000c3")
MISTO = uuid.UUID("00000000-0000-0000-0000-0000000000c4")
SERIAL_SECRETO = "SERIAL-SECRETO-XYZ"
NOME_SECRETO = "Usina Nome Secreto"
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_ENGINES: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    while _ENGINES:
        await _ENGINES.pop().dispose()


def _filled(model: type, **given: Any):
    """Instância com as colunas obrigatórias sem valor padrão preenchidas por tipo."""
    values: dict[str, Any] = dict(given)
    table: Table = model.__table__  # type: ignore[attr-defined]
    for column in table.columns:
        if column.name in values or column.nullable:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        py = column.type.python_type
        length = getattr(column.type, "length", None) or 40
        if issubclass(py, enum.Enum):
            values[column.name] = list(py)[0]
        elif py is str:
            values[column.name] = uuid.uuid4().hex[: min(length, 7 if length < 12 else 32)]
        elif py is bool:
            values[column.name] = True
        elif py is int:
            values[column.name] = 1
        elif py is Decimal:
            values[column.name] = Decimal("1")
        elif py is float:
            values[column.name] = 1.0
        elif py is dt.datetime:
            values[column.name] = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        elif py is dt.date:
            values[column.name] = dt.date(2026, 1, 1)
        elif py is bytes:
            values[column.name] = b"x"
        elif py in (dict, list):
            values[column.name] = {} if py is dict else []
        else:  # pragma: no cover
            raise AssertionError(f"tipo sem preenchimento: {column.name} {py}")
    return model(**values)


async def _seed_plant(
    session, plant_id, org_id, provider, *, name, with_account=True, account_provider=None
):
    session.add(Plant(id=plant_id, organization_id=org_id, name=name))
    await session.flush()
    if with_account:
        session.add(
            ProviderAccountRecord(
                plant_id=plant_id,
                provider=account_provider or provider,
                login_hint="login-secreto@example.com",
                account_fingerprint=uuid.uuid4().hex,
                ciphertext=b"cifrado",
                key_version=1,
                active=True,
            )
        )
    device = Device(
        plant_id=plant_id, provider=provider, serial_number=SERIAL_SECRETO + uuid.uuid4().hex
    )
    session.add(device)
    await session.flush()
    energy = DailyEnergy(
        device_id=device.id,
        production_date=dt.date(2026, 1, 1),
        energy_kwh=Decimal("10"),
        source="GROWATT_TOTAL_DIFF" if provider.startswith("GROWATT") else "NEPVIEWER_V2",
    )
    session.add(energy)
    await session.flush()
    session.add(
        DailyEnergyVersion(
            daily_energy_id=energy.id, energy_kwh=Decimal("9"), status=energy.status
        )
    )
    session.add(
        MeterReading(
            plant_id=plant_id,
            device_id=device.id,
            reading_date=dt.date(2026, 1, 1),
            total_kwh=Decimal("5"),
            source="x",
        )
    )
    session.add(
        ProviderPlantClaimRecord(
            plant_id=plant_id,
            provider_family="GROWATT" if provider.startswith("GROWATT") else "NEPVIEWER",
            serial_number=uuid.uuid4().hex,
        )
    )
    bill = _filled(UtilityBillRecord, plant_id=plant_id)
    session.add(bill)
    await session.flush()
    session.add(_filled(MonthlyReportSnapshotRecord, plant_id=plant_id, bill_id=bill.id))
    execution = _filled(PipelineExecutionRecord, plant_id=plant_id)
    session.add(execution)
    await session.flush()
    # Auditoria ligada à usina: pela usina, pela fatura, pela execução e por details.plant_id.
    for resource_type, resource_id, details in (
        ("plant", str(plant_id), {}),
        ("utility_bill", str(bill.id), {}),
        ("pipeline_execution", str(execution.id), {}),
        ("organization", str(org_id), {"plant_id": str(plant_id)}),
        # UUID da usina em chave aninhada de details (não só details.plant_id).
        ("organization", str(org_id), {"a": {"b": [f"x {plant_id} y"]}}),
    ):
        session.add(
            AuditEventRecord(
                organization_id=org_id,
                action="x.y",
                resource_type=resource_type,
                resource_id=resource_id,
                outcome="success",
                actor_role="ADMIN",
                actor_credential_id="c",
                details=details,
            )
        )
    for model in (
        ReportExportTask,
        CollectionTaskRecord,
        OutboxEventRecord,
        AlertDeliveryRecord,
        DailyClimateObservationRecord,
        DailySolarModelResultRecord,
        DailyPvPerformanceRecord,
        SeasonalPvBaselineRecord,
        DailyPvLossAssessmentRecord,
    ):
        session.add(_filled(model, plant_id=plant_id))
    await session.flush()


async def _seed_world(
    session,
    org_a,
    org_b,
    gw,
    nep_a,
    nep_b,
    *,
    nep_in_gw_plant=False,
    gw_without_account=False,
    gw_account_provider=None,
    nep_claim_in_gw=False,
    source_only_plant=None,
):
    session.add_all(
        [
            OrganizationRecord(id=org_a, name="A", slug=f"purge-{org_a.hex}", active=True),
            OrganizationRecord(id=org_b, name="B", slug=f"purge-{org_b.hex}", active=True),
        ]
    )
    await session.flush()
    await _seed_plant(
        session,
        gw,
        org_a,
        "GROWATT_TOKEN",
        name=NOME_SECRETO,
        with_account=not gw_without_account,
        account_provider=gw_account_provider,
    )
    if source_only_plant is not None:
        # Aparelho NEPViewer com produção de origem Growatt: selecionada pela origem e recusada.
        await _seed_plant(session, source_only_plant, org_b, "NEPVIEWER", name="Misto")
        energy = (
            await session.execute(
                select(DailyEnergy)
                .join(Device, Device.id == DailyEnergy.device_id)
                .where(Device.plant_id == source_only_plant)
            )
        ).scalar_one()
        energy.source = "GROWATT_TOTAL_DIFF"
    await _seed_plant(session, nep_a, org_a, "NEPVIEWER", name="Nep A")
    await _seed_plant(session, nep_b, org_b, "NEPVIEWER", name="Nep B")
    # Texto que só PARECE conter o UUID (hex a mais colado no fim): não é da usina, fica.
    session.add(
        AuditEventRecord(
            organization_id=org_a,
            action="x.boundary",
            resource_type="organization",
            resource_id=str(org_a),
            outcome="success",
            actor_role="ADMIN",
            actor_credential_id="c",
            details={"nota": f"{gw}0"},
        )
    )
    if nep_claim_in_gw:
        session.add(
            ProviderPlantClaimRecord(
                plant_id=gw, provider_family="NEPVIEWER", serial_number=uuid.uuid4().hex
            )
        )
    for org_id in (org_a, org_b):
        session.add(_filled(OperationalUserRecord, organization_id=org_id))
    if nep_in_gw_plant:
        session.add(Device(plant_id=gw, provider="NEPVIEWER", serial_number="NEP-1"))
    org = await session.get(OrganizationRecord, org_a)
    assert org is not None
    org.default_plant_id = gw
    session.add(
        _filled(ApiCredentialRecord, organization_id=org_a, plant_ids=[str(gw), str(nep_a)])
    )
    session.add(
        _filled(ApiCredentialRecord, organization_id=org_a, plant_ids=[str(gw)])
    )



async def _factory(**world: Any):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _seed_world(
            session,
            ORG_A,
            ORG_B,
            GW,
            NEP_A,
            NEP_B,
            **world,
        )
        await session.commit()
    return factory


def _use(monkeypatch, factory) -> None:
    monkeypatch.setattr(cloud_jobs, "SessionFactory", factory)


async def _counts(factory) -> dict[str, int]:
    async with factory() as session:
        return {
            name: int((await session.execute(select(func.count()).select_from(t))).scalar_one())
            for name, t in Base.metadata.tables.items()
        }


async def _untouched_rows(factory) -> dict[str, list[tuple[Any, ...]]]:
    ids = [NEP_A, NEP_B]
    async with factory() as session:
        dump = {}
        for cat in CATEGORIES:
            rows = (await session.execute(select(cat.table).where(cat.owned(ids)))).all()
            dump[cat.name] = sorted((tuple(map(repr, r)) for r in rows))
        return dump


async def _referencias(factory) -> dict[str, Any]:
    """Referências de usuário/organização que a exclusão ajusta (para provar o rollback)."""
    async with factory() as session:
        org = await session.get(OrganizationRecord, ORG_A)
        assert org is not None
        creds = (
            await session.execute(
                select(
                    ApiCredentialRecord.id,
                    ApiCredentialRecord.plant_ids,
                    ApiCredentialRecord.active,
                    ApiCredentialRecord.revoked_at,
                )
            )
        ).all()
        return {"default": org.default_plant_id, "creds": sorted(map(repr, creds))}


async def _org_b(factory) -> list[str]:
    async with factory() as session:
        orgs = (
            await session.execute(select(OrganizationRecord).where(OrganizationRecord.id == ORG_B))
        ).scalars().all()
        users = (
            await session.execute(
                select(OperationalUserRecord).where(OperationalUserRecord.organization_id == ORG_B)
            )
        ).scalars().all()
        assert orgs and users
        return sorted(
            repr({c.name: getattr(row, c.name) for c in row.__table__.columns})
            for row in [*orgs, *users]
        )


async def _auditoria_nep(factory) -> list[str]:
    nep = {str(NEP_A), str(NEP_B)}
    async with factory() as session:
        rows = (await session.execute(select(AuditEventRecord))).scalars().all()
        return sorted(
            repr((r.id, r.resource_type, r.resource_id, r.details))
            for r in rows
            if r.resource_id in nep or str(r.details.get("plant_id")) in nep
        )


async def test_simulacao_nao_grava_e_conta(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    before = await _counts(factory)
    out = await run_purge_discontinued_plants()
    assert await _counts(factory) == before
    assert "usinas_selecionadas=1" in out
    assert "usinas_nao_selecionadas_intocadas=2" in out
    for cat in CATEGORIES:
        assert f"seriam_excluidos.{cat.name}=1" in out
    assert "eventos_de_auditoria_excluidos=5" in out
    assert "organizacoes_com_usina_padrao_ajustada=1" in out
    assert "credenciais_com_escopo_ajustado=2" in out
    assert "credenciais_revogadas_por_escopo_vazio=1" in out


async def test_aplicar_apaga_tudo_da_usina_growatt_e_preserva_o_resto(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    before = await _counts(factory)
    untouched = await _untouched_rows(factory)
    org_b = await _org_b(factory)
    audit_nep = await _auditoria_nep(factory)

    out = await run_purge_discontinued_plants(apply=True, confirm_plant_count=1)

    assert "aplicado" in out and "excluidos.utility_bills=1" in out
    assert "eventos_de_auditoria_excluidos=5" in out
    after = await _counts(factory)
    for cat in CATEGORIES:
        assert after[cat.table.name] == before[cat.table.name] - 1, cat.name
    for name, table in PRESERVED_TABLES:
        assert after[table.name] == before[table.name], name
    # Auditoria: saem os 5 eventos ligados à usina e entra o evento de plataforma.
    assert after["audit_events"] == before["audit_events"] - 5 + 1
    assert await _untouched_rows(factory) == untouched
    assert await _org_b(factory) == org_b
    assert await _auditoria_nep(factory) == audit_nep
    async with factory() as session:
        assert await session.get(Plant, GW) is None
        # Nenhum evento cita o UUID da usina (nem aninhado); o texto com hex a mais fica.
        todos = (await session.execute(select(AuditEventRecord))).scalars().all()
        assert [e for e in todos if str(GW) in repr(e.details) + str(e.resource_id)
                and not e.details.get("nota")] == []
        assert any(e.action == "x.boundary" for e in todos)
        org = await session.get(OrganizationRecord, ORG_A)
        assert org is not None and org.default_plant_id is None
        creds = (
            await session.execute(
                select(
                    ApiCredentialRecord.plant_ids,
                    ApiCredentialRecord.active,
                    ApiCredentialRecord.revoked_at,
                )
            )
        ).all()
        by_len = sorted(creds, key=lambda c: len(c.plant_ids))
        # Escopo que ficou vazio: revogada, lista [] (nunca NULL = organização inteira).
        assert by_len[0].plant_ids == [] and by_len[0].active is False
        assert by_len[0].revoked_at is not None
        assert by_len[1].plant_ids == [str(NEP_A)] and by_len[1].active is True
        assert by_len[1].revoked_at is None
        event = (
            await session.execute(
                select(AuditEventRecord).where(AuditEventRecord.action == AUDIT_ACTION)
            )
        ).scalar_one()
        assert event.organization_id is None and event.resource_id is None
        assert event.details == {"plants": 1, "reason": "provider_discontinued", "adr": "ADR-101"}


async def test_idempotente_segunda_execucao_nao_muda_nada(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    await run_purge_discontinued_plants(apply=True, confirm_plant_count=1)
    after_first = await _counts(factory)
    out = await run_purge_discontinued_plants(apply=True, confirm_plant_count=0)
    assert "usinas_selecionadas=0" in out
    assert await _counts(factory) == after_first


async def test_selecao_por_aparelho_sem_conexao(monkeypatch) -> None:
    factory = await _factory(gw_without_account=True)
    _use(monkeypatch, factory)
    out = await run_purge_discontinued_plants()
    assert "usinas_selecionadas=1" in out


@pytest.mark.parametrize(
    "world",
    [
        {"nep_in_gw_plant": True},  # aparelho NEPViewer na usina Growatt
        {"gw_account_provider": "NEPVIEWER"},  # conexão NEPViewer na usina Growatt
        {"nep_claim_in_gw": True},  # reserva NEPViewer na usina Growatt
        {"source_only_plant": MISTO},  # só a origem da produção é Growatt; aparelho é NEP
    ],
    ids=["aparelho", "conexao", "reserva", "so_origem_da_producao"],
)
async def test_recusa_se_usina_selecionada_tem_outra_marca(monkeypatch, world) -> None:
    factory = await _factory(**world)
    _use(monkeypatch, factory)
    before = await _counts(factory)
    for apply in (False, True):
        with pytest.raises(OperatorError) as info:
            await run_purge_discontinued_plants(apply=apply, confirm_plant_count=2)
        assert "recusado: 1 usina" in str(info.value)
        assert not UUID_RE.search(str(info.value))
    assert await _counts(factory) == before


async def test_recusa_se_quantidade_confirmada_diverge(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    before = await _counts(factory)
    with pytest.raises(OperatorError):
        await run_purge_discontinued_plants(apply=True, confirm_plant_count=2)
    with pytest.raises(OperatorError):
        await run_purge_discontinued_plants(apply=True, confirm_plant_count=None)
    assert await _counts(factory) == before


async def test_falha_na_verificacao_desfaz_tudo(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    before = await _counts(factory)
    refs = await _referencias(factory)
    import mplacas.providers.purge_discontinued as module

    real = module._verify

    async def stray_row(session, plan, deleted):
        # Uma organização a mais no meio da transação: a conferência tem de barrar.
        session.add(OrganizationRecord(name="X", slug="x", active=True))
        await session.flush()
        await real(session, plan, deleted)

    monkeypatch.setattr(module, "_verify", stray_row)
    with pytest.raises(OperatorError):
        await run_purge_discontinued_plants(apply=True, confirm_plant_count=1)
    assert await _counts(factory) == before
    # default_plant_id, plant_ids e active/revoked_at das credenciais voltaram.
    assert await _referencias(factory) == refs
    assert refs["default"] == GW


async def test_falha_no_meio_do_delete_desfaz_tudo(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    before = await _counts(factory)
    refs = await _referencias(factory)
    import mplacas.providers.purge_discontinued as module

    real_delete = module.delete
    calls = {"n": 0}

    def breaking(table):
        calls["n"] += 1
        if calls["n"] == 8:
            raise IntegrityError("DELETE", {}, Exception("fk"))
        return real_delete(table)

    monkeypatch.setattr(module, "delete", breaking)
    with pytest.raises(IntegrityError):
        await run_purge_discontinued_plants(apply=True, confirm_plant_count=1)
    assert calls["n"] == 8
    assert await _counts(factory) == before
    assert await _referencias(factory) == refs


async def test_saida_publica_nao_contem_uuid_serial_nome_nem_login(monkeypatch) -> None:
    factory = await _factory()
    _use(monkeypatch, factory)
    out = await run_purge_discontinued_plants()
    out += await run_purge_discontinued_plants(apply=True, confirm_plant_count=1)
    assert "usinas_selecionadas=1" in out
    assert not UUID_RE.search(out)
    for secret in (SERIAL_SECRETO, NOME_SECRETO, "login-secreto", "example.com"):
        assert secret not in out


def test_parser_aceita_os_argumentos_do_comando() -> None:
    args = _build_parser().parse_args(
        ["purge-discontinued-plants", "--apply", "--confirm-plant-count", "1", "--totals-only"]
    )
    assert args.apply and args.confirm_plant_count == 1 and args.totals_only


def test_apply_sem_confirmacao_falha_antes_de_tocar_no_banco() -> None:
    args = _build_parser().parse_args(["purge-discontinued-plants", "--apply"])
    with pytest.raises(OperatorError):
        args.handler(args)


def test_todas_as_tabelas_ligadas_a_usina_estao_na_lista_de_exclusao() -> None:
    covered = {cat.table.name for cat in CATEGORIES}
    # organizations.default_plant_id é tratada à parte (vira NULL).
    tratadas_a_parte = {"organizations"}
    missing: set[str] = set()
    for table in Base.metadata.tables.values():
        if table.name in covered | tratadas_a_parte:
            continue
        # FK cujo destino é qualquer categoria apagada.
        for fk in table.foreign_keys:
            if fk.column.table.name in covered:
                missing.add(table.name)
        # Coluna de dono sem FK declarada (referência "solta" por nome).
        for column in table.columns:
            if column.name in {"plant_id", "device_id", "bill_id", "daily_energy_id"}:
                missing.add(table.name)
    assert sorted(missing) == []


async def test_segunda_passada_com_ids_diferentes_recusa(monkeypatch) -> None:
    import mplacas.providers.purge_discontinued as module

    factory = await _factory()
    chamadas = {"n": 0}

    async def instavel(session):
        chamadas["n"] += 1
        return ((GW,) if chamadas["n"] == 1 else (GW, NEP_A)), 0

    monkeypatch.setattr(module, "select_discontinued_plants", instavel)
    monkeypatch.setattr(module, "_is_postgresql", lambda _session: True)
    async with factory() as session:
        with pytest.raises(module.PurgeError) as info:
            await module.build_plan(session, lock=True)
    assert "mudou durante a trava" in str(info.value)
    assert chamadas["n"] == 2
