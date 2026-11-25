"""Exclusão definitiva das usinas conectadas por marca descontinuada (ADR-101).

Decisão do dono (25/11/2026): toda usina conectada pela Growatt é apagada por
inteiro e para sempre — faturas confirmadas e relatórios mensais incluídos. As
usinas da NEPViewer não são tocadas. Este módulo é a **única** via dessa
exclusão: nunca por migração nem por SQL avulso.

O repositório é público e o log do job também: nada aqui devolve id de usina,
nome, serial, coordenada, login ou valor — só contagens por categoria.

Contexto de plataforma definido por quem chama; **este módulo não faz commit**.
Quem chama decide: simulação termina sem commit, aplicação faz commit só se
``execute_purge`` não levantar ``PurgeError``.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, Table, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from mplacas.alerts.db_models import AlertDeliveryRecord
from mplacas.audit.db_models import AuditEventRecord
from mplacas.billing.db_models import UtilityBillRecord
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.collection.db_models import CollectionTaskRecord
from mplacas.credentials.db_models import ApiCredentialRecord, OperationalUserRecord
from mplacas.db.models import DailyEnergy, DailyEnergyVersion, Device, MeterReading, Plant
from mplacas.events.db_models import OutboxEventRecord
from mplacas.orchestration.db_models import PipelineExecutionRecord
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.providers.accounts import DISCONTINUED_PROVIDERS
from mplacas.providers.db_models import ProviderAccountRecord, ProviderPlantClaimRecord
from mplacas.reports.db_models import MonthlyReportSnapshotRecord, ReportExportTask

GROWATT_PREFIX = "GROWATT"
AUDIT_ACTION = "plant.purged_discontinued_provider"
AUDIT_ADR = "ADR-101"
AUDIT_REASON = "provider_discontinued"


class PurgeError(RuntimeError):
    """Recusa ou falha de verificação. O texto é escrito aqui e é seguro para o log público."""


@dataclass(frozen=True, slots=True)
class _Category:
    name: str
    table: Table
    owned: Callable[[Sequence[uuid.UUID]], ColumnElement[bool]]


def _table(model: Any) -> Table:
    table = model.__table__
    assert isinstance(table, Table)
    return table


def _by_plant(model: Any, column: str = "plant_id") -> Callable[
    [Sequence[uuid.UUID]], ColumnElement[bool]
]:
    def owned(ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        result: ColumnElement[bool] = getattr(model, column).in_(ids)
        return result

    return owned


# Ordem de exclusão (filhos antes dos pais). As FKs RESTRICT para ``plants`` e
# ``utility_bills`` (faturas, relatórios, exportações, tarefas de coleta, outbox)
# exigem exclusão explícita; as CASCADE são apagadas explicitamente também, para
# serem contadas e verificadas uma a uma.
CATEGORIES: tuple[_Category, ...] = (
    _Category(
        "daily_energy_versions",
        _table(DailyEnergyVersion),
        lambda ids: DailyEnergyVersion.daily_energy_id.in_(
            select(DailyEnergy.id).where(
                DailyEnergy.device_id.in_(select(Device.id).where(Device.plant_id.in_(ids)))
            )
        ),
    ),
    _Category(
        "daily_energy",
        _table(DailyEnergy),
        lambda ids: DailyEnergy.device_id.in_(select(Device.id).where(Device.plant_id.in_(ids))),
    ),
    _Category("meter_readings", _table(MeterReading), _by_plant(MeterReading)),
    # RESTRICT para utility_bills: relatório antes da fatura.
    _Category(
        "monthly_report_snapshots",
        _table(MonthlyReportSnapshotRecord),
        _by_plant(MonthlyReportSnapshotRecord),
    ),
    _Category("report_export_tasks", _table(ReportExportTask), _by_plant(ReportExportTask)),
    _Category("utility_bills", _table(UtilityBillRecord), _by_plant(UtilityBillRecord)),
    _Category("collection_tasks", _table(CollectionTaskRecord), _by_plant(CollectionTaskRecord)),
    _Category("outbox_events", _table(OutboxEventRecord), _by_plant(OutboxEventRecord)),
    _Category(
        "alert_delivery_records", _table(AlertDeliveryRecord), _by_plant(AlertDeliveryRecord)
    ),
    _Category(
        "daily_climate_observations",
        _table(DailyClimateObservationRecord),
        _by_plant(DailyClimateObservationRecord),
    ),
    _Category(
        "daily_solar_model_results",
        _table(DailySolarModelResultRecord),
        _by_plant(DailySolarModelResultRecord),
    ),
    _Category(
        "daily_pv_performance_results",
        _table(DailyPvPerformanceRecord),
        _by_plant(DailyPvPerformanceRecord),
    ),
    _Category(
        "seasonal_pv_baseline_results",
        _table(SeasonalPvBaselineRecord),
        _by_plant(SeasonalPvBaselineRecord),
    ),
    _Category(
        "daily_pv_loss_assessments",
        _table(DailyPvLossAssessmentRecord),
        _by_plant(DailyPvLossAssessmentRecord),
    ),
    _Category(
        "pipeline_executions", _table(PipelineExecutionRecord), _by_plant(PipelineExecutionRecord)
    ),
    _Category(
        "provider_plant_claims",
        _table(ProviderPlantClaimRecord),
        _by_plant(ProviderPlantClaimRecord),
    ),
    # A credencial cifrada vai embora junto com a linha.
    _Category("provider_accounts", _table(ProviderAccountRecord), _by_plant(ProviderAccountRecord)),
    _Category("devices", _table(Device), _by_plant(Device)),
    _Category("plants", _table(Plant), _by_plant(Plant, "id")),
)

# Tabelas que NÃO podem mudar de tamanho (usuários, organizações, credenciais,
# convites). A auditoria é conferida à parte em ``_verify``: sai só o que foi levantado
# (eventos ligados às usinas, conferidos por id) e entra um único evento de plataforma.
PRESERVED_TABLES: tuple[tuple[str, Table], ...] = (
    ("organizations", _table(OrganizationRecord)),
    ("operational_users", _table(OperationalUserRecord)),
    ("api_credentials", _table(ApiCredentialRecord)),
    ("user_invitations", _table(UserInvitationRecord)),
)


def _is_growatt(column: Any) -> ColumnElement[bool]:
    result: ColumnElement[bool] = column.startswith(GROWATT_PREFIX)
    return result


@dataclass(frozen=True, slots=True)
class PurgePlan:
    plant_ids: tuple[uuid.UUID, ...]
    refused_plants: int
    owned: dict[str, int]
    totals_before: dict[str, int]
    preserved_before: dict[str, int]
    plants_untouched: int
    default_plant_orgs: int
    scoped_credentials: int
    scoped_credentials_revoked: int
    audit_ids: tuple[uuid.UUID, ...]
    # Capturados antes do DELETE: a re-checagem da auditoria não consulta o que já sumiu.
    bill_ids: frozenset[str]
    execution_ids: frozenset[str]

    @property
    def selected(self) -> int:
        return len(self.plant_ids)


@dataclass(frozen=True, slots=True)
class PurgeResult:
    plan: PurgePlan
    deleted: dict[str, int] = field(default_factory=dict)


async def select_discontinued_plants(session: AsyncSession) -> tuple[tuple[uuid.UUID, ...], int]:
    """Usinas conectadas pela marca descontinuada e quantas delas a recusa barra.

    Seleciona por conexão (ativa ou não) de marca descontinuada, por aparelho
    ``GROWATT*`` ou por produção com origem ``GROWATT*``. Retorna ``(ids, recusadas)``:
    ``recusadas`` > 0 quando alguma selecionada também tem conexão, reserva ou aparelho
    de outra marca (a execução inteira é recusada).
    """
    from_accounts = select(ProviderAccountRecord.plant_id).where(
        ProviderAccountRecord.provider.in_(sorted(DISCONTINUED_PROVIDERS))
        | _is_growatt(ProviderAccountRecord.provider)
    )
    from_devices = select(Device.plant_id).where(_is_growatt(Device.provider))
    from_energy = (
        select(Device.plant_id)
        .join(DailyEnergy, DailyEnergy.device_id == Device.id)
        .where(_is_growatt(DailyEnergy.source))
    )
    selected = {
        row[0]
        for query in (from_accounts, from_devices, from_energy)
        for row in (await session.execute(query)).all()
    }
    ids = tuple(sorted(selected, key=str))
    if not ids:
        return ids, 0

    foreign: set[uuid.UUID] = set()
    queries = (
        select(ProviderAccountRecord.plant_id).where(
            ProviderAccountRecord.plant_id.in_(ids),
            ProviderAccountRecord.provider.not_in(sorted(DISCONTINUED_PROVIDERS)),
            ~_is_growatt(ProviderAccountRecord.provider),
        ),
        select(Device.plant_id).where(Device.plant_id.in_(ids), ~_is_growatt(Device.provider)),
        select(ProviderPlantClaimRecord.plant_id).where(
            ProviderPlantClaimRecord.plant_id.in_(ids),
            ~_is_growatt(ProviderPlantClaimRecord.provider_family),
        ),
    )
    for query in queries:
        foreign.update(row[0] for row in (await session.execute(query)).all())
    return ids, len(foreign)


async def _count(session: AsyncSession, table: Table, where: ColumnElement[bool] | None) -> int:
    query = select(func.count()).select_from(table)
    if where is not None:
        query = query.where(where)
    return int((await session.execute(query)).scalar_one())


async def _scoped_credentials(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> list[tuple[uuid.UUID, bool, list[str]]]:
    """Credenciais com escopo de usina que citam alguma das usinas: (id, ativa, lista depois)."""
    wanted = {str(plant_id) for plant_id in ids}
    rows = (
        await session.execute(
            select(
                ApiCredentialRecord.id, ApiCredentialRecord.active, ApiCredentialRecord.plant_ids
            ).where(ApiCredentialRecord.plant_ids.is_not(None))
        )
    ).all()
    found: list[tuple[uuid.UUID, bool, list[str]]] = []
    for credential_id, active, plant_ids in rows:
        current = [str(item) for item in plant_ids or []]
        if wanted & set(current):
            found.append((credential_id, bool(active), [i for i in current if i not in wanted]))
    return found


# Tipos de recurso da auditoria ligados a usina (levantamento em ``resource_type=`` dos
# routers): ``plant`` (resource_id = usina), ``utility_bill`` (= fatura) e
# ``pipeline_execution`` (= execução do pipeline da usina). ``organization``,
# ``api_credential``, ``user_invitation`` e ``operational_user`` não são da usina e ficam
# (salvo se ``details.plant_id`` citar a usina, caso de ``plant.created_from_connection``).
def _mentions_plant(details: object, plants: set[str]) -> bool:
    """O texto de ``details`` (qualquer chave, inclusive aninhada) cita o UUID de uma usina.

    Regex exata do UUID em minúsculas, com limites (não vale pedaço de outro identificador).
    """
    text = json.dumps(details, default=str, sort_keys=True).lower()
    return any(
        re.search(rf"(?<![0-9a-f-]){re.escape(plant)}(?![0-9a-f-])", text) for plant in plants
    )


async def _owned_resource_ids(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> tuple[frozenset[str], frozenset[str]]:
    """Ids (texto) das faturas e das execuções do pipeline das usinas, antes do DELETE."""
    bills = frozenset(
        str(row[0])
        for row in (
            await session.execute(
                select(UtilityBillRecord.id).where(UtilityBillRecord.plant_id.in_(ids))
            )
        ).all()
    )
    executions = frozenset(
        str(row[0])
        for row in (
            await session.execute(
                select(PipelineExecutionRecord.id).where(PipelineExecutionRecord.plant_id.in_(ids))
            )
        ).all()
    )
    return bills, executions


async def _audit_ids_of(
    session: AsyncSession,
    ids: Sequence[uuid.UUID],
    bills: frozenset[str],
    executions: frozenset[str],
) -> tuple[uuid.UUID, ...]:
    plants = {str(plant_id) for plant_id in ids}
    by_resource = (
        (AuditEventRecord.resource_type == "plant") & AuditEventRecord.resource_id.in_(plants)
    ) | (
        (AuditEventRecord.resource_type == "utility_bill")
        & AuditEventRecord.resource_id.in_(bills)
    ) | (
        (AuditEventRecord.resource_type == "pipeline_execution")
        & AuditEventRecord.resource_id.in_(executions)
    )
    # ``details`` é JSON: filtra em SQL por texto (portável SQLite/PostgreSQL) e confere em Python.
    by_details = or_(
        *(cast(AuditEventRecord.details, String).like(f"%{plant_id}%") for plant_id in plants)
    )
    rows = (
        await session.execute(
            select(
                AuditEventRecord.id,
                AuditEventRecord.resource_type,
                AuditEventRecord.resource_id,
                AuditEventRecord.details,
            ).where(by_resource | by_details)
        )
    ).all()
    found: list[uuid.UUID] = []
    for audit_id, resource_type, resource_id, details in rows:
        in_details = _mentions_plant(details, plants)
        in_resource = (
            (resource_type == "plant" and resource_id in plants)
            or (resource_type == "utility_bill" and resource_id in bills)
            or (resource_type == "pipeline_execution" and resource_id in executions)
        )
        if in_details or in_resource:
            found.append(audit_id)
    return tuple(sorted(found, key=str))


def _is_postgresql(session: AsyncSession) -> bool:
    bind = session.get_bind()
    return bool(bind is not None and bind.dialect.name == "postgresql")


async def build_plan(session: AsyncSession, *, lock: bool = False) -> PurgePlan:
    """Lê e conta; não grava. Levanta ``PurgeError`` se a seleção deve ser recusada.

    ``lock``: na PostgreSQL trava as linhas das usinas selecionadas (``FOR UPDATE``) e
    reavalia seleção e recusa já com a trava, para uma conexão concorrente não mudar o
    quadro entre a leitura e a exclusão. No SQLite não há o que travar.
    """
    ids, refused = await select_discontinued_plants(session)
    if lock and ids and _is_postgresql(session):
        await session.execute(select(Plant.id).where(Plant.id.in_(ids)).with_for_update())
        first = ids
        ids, refused = await select_discontinued_plants(session)
        if ids != first:
            raise PurgeError(
                "recusado: a selecao mudou durante a trava; nada foi gravado "
                "(repita o comando)"
            )
    if refused:
        raise PurgeError(
            f"recusado: {refused} usina(s) selecionada(s) tem conexao, reserva ou aparelho "
            "de outra marca; nada foi gravado"
        )
    owned: dict[str, int] = {}
    totals: dict[str, int] = {}
    for category in CATEGORIES:
        totals[category.name] = await _count(session, category.table, None)
        owned[category.name] = (
            await _count(session, category.table, category.owned(ids)) if ids else 0
        )
    preserved = {name: await _count(session, table, None) for name, table in PRESERVED_TABLES}
    bills, executions = (
        await _owned_resource_ids(session, ids) if ids else (frozenset[str](), frozenset[str]())
    )
    scoped = await _scoped_credentials(session, ids) if ids else []
    default_orgs = (
        await _count(
            session,
            _table(OrganizationRecord),
            OrganizationRecord.default_plant_id.in_(ids),
        )
        if ids
        else 0
    )
    return PurgePlan(
        plant_ids=ids,
        refused_plants=0,
        owned=owned,
        totals_before=totals,
        preserved_before=preserved,
        plants_untouched=totals["plants"] - owned["plants"],
        default_plant_orgs=default_orgs,
        scoped_credentials=len(scoped),
        scoped_credentials_revoked=sum(1 for _, active, after in scoped if active and not after),
        audit_ids=await _audit_ids_of(session, ids, bills, executions) if ids else (),
        bill_ids=bills,
        execution_ids=executions,
    )


async def execute_purge(session: AsyncSession, plan: PurgePlan) -> PurgeResult:
    """Apaga na ordem segura e confere tudo; levanta ``PurgeError`` se algo diferir.

    Não faz commit: o chamador só confirma se esta função retornar. Usuários e
    organizações não são apagados. Os eventos de auditoria ligados às usinas (e aos
    recursos apagados) são apagados junto, por decisão do dono; fica só o evento de
    plataforma desta execução, com contagens.
    """
    ids = plan.plant_ids
    if not ids:
        return PurgeResult(plan=plan)

    # Referências de usuários/organizações que não podem ficar apontando para o nada.
    await session.execute(
        update(OrganizationRecord)
        .where(OrganizationRecord.default_plant_id.in_(ids))
        .values(default_plant_id=None)
    )
    now = datetime.now(UTC)
    for credential_id, active, after in await _scoped_credentials(session, ids):
        values: dict[str, Any] = {"plant_ids": after}
        if not after:
            # Escopo vazio não pode ficar ativo: NULL seria "organização inteira" e a
            # lista vazia não é um escopo válido para uma chave em uso. Revoga como
            # ``CredentialService.revoke`` (active=False + revoked_at) e mantém ``[]``.
            values["active"] = False
            if active:
                values["revoked_at"] = now
        await session.execute(
            update(ApiCredentialRecord)
            .where(ApiCredentialRecord.id == credential_id)
            .values(**values)
        )

    audit_table = _table(AuditEventRecord)
    audit_deleted = 0
    for start in range(0, len(plan.audit_ids), 500):
        chunk = plan.audit_ids[start : start + 500]
        result = await session.execute(
            delete(audit_table).where(AuditEventRecord.id.in_(chunk))
        )
        audit_deleted += int(getattr(result, "rowcount", -1))

    deleted: dict[str, int] = {}
    for category in CATEGORIES:
        result = await session.execute(delete(category.table).where(category.owned(ids)))
        deleted[category.name] = int(getattr(result, "rowcount", -1))
    deleted["audit_events"] = audit_deleted

    await _verify(session, plan, deleted)

    event = AuditEventRecord(
        organization_id=None,
        action=AUDIT_ACTION,
        resource_type="platform",
        resource_id=None,
        outcome="success",
        actor_role="PLATFORM",
        actor_credential_id="cloud_jobs:purge-discontinued-plants",
        request_id=None,
        details={
            "plants": plan.selected,
            "reason": AUDIT_REASON,
            "adr": AUDIT_ADR,
        },
    )
    session.add(event)
    await session.flush()
    # Exatamente um evento de plataforma novo, conferido por id (o total global da tabela
    # muda com qualquer requisição da API durante a transação, então não é conferido).
    if await _count(session, audit_table, AuditEventRecord.id == event.id) != 1:
        raise PurgeError("verificacao falhou (auditoria); transacao desfeita, nada foi gravado")
    return PurgeResult(plan=plan, deleted=deleted)


async def _verify(session: AsyncSession, plan: PurgePlan, deleted: dict[str, int]) -> None:
    ids = plan.plant_ids
    problems = 0
    for category in CATEGORIES:
        if deleted[category.name] != plan.owned[category.name]:
            problems += 1
        if await _count(session, category.table, category.owned(ids)) != 0:
            problems += 1
        # Tudo que não era das usinas selecionadas segue com a mesma contagem.
        expected = plan.totals_before[category.name] - plan.owned[category.name]
        if await _count(session, category.table, None) != expected:
            problems += 1
    for name, table in PRESERVED_TABLES:
        if await _count(session, table, None) != plan.preserved_before[name]:
            problems += 1
    # Auditoria: saiu exatamente o que foi levantado (o evento de plataforma entra depois).
    audit_table = _table(AuditEventRecord)
    if deleted["audit_events"] != len(plan.audit_ids):
        problems += 1
    for start in range(0, len(plan.audit_ids), 500):
        chunk = plan.audit_ids[start : start + 500]
        if await _count(session, audit_table, AuditEventRecord.id.in_(chunk)) != 0:
            problems += 1
    if await _audit_ids_of(session, ids, plan.bill_ids, plan.execution_ids):
        problems += 1
    if (
        await _count(
            session, _table(OrganizationRecord), OrganizationRecord.default_plant_id.in_(ids)
        )
        != 0
    ):
        problems += 1
    if await _scoped_credentials(session, ids):
        problems += 1
    if problems:
        raise PurgeError(
            f"verificacao falhou ({problems} divergencia(s)); transacao desfeita, nada foi gravado"
        )


def render_plan(plan: PurgePlan, *, applied: bool, deleted: dict[str, int] | None = None) -> str:
    """Só contagens agregadas por categoria — nunca nome, id, serial, valor ou coordenada."""
    mode = "aplicado" if applied else "simulacao (nada foi gravado)"
    counts = deleted if deleted is not None else plan.owned
    verb = "excluidos" if applied else "seriam_excluidos"
    lines = [
        f"Exclusao definitiva de usinas de marca descontinuada ({AUDIT_ADR}) - {mode}",
        f"usinas_selecionadas={plan.selected}",
        f"usinas_nao_selecionadas_intocadas={plan.plants_untouched}",
    ]
    for category in CATEGORIES:
        lines.append(f"{verb}.{category.name}={counts.get(category.name, 0)}")
    lines.extend(
        [
            f"eventos_de_auditoria_excluidos={len(plan.audit_ids)}",
            f"organizacoes_com_usina_padrao_ajustada={plan.default_plant_orgs}",
            f"credenciais_com_escopo_ajustado={plan.scoped_credentials}",
            f"credenciais_revogadas_por_escopo_vazio={plan.scoped_credentials_revoked}",
        ]
    )
    return "\n".join(lines)
