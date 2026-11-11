"""Relatório somente leitura: usinas Growatt reservadas por mais de uma conexão.

Contexto: duas organizações podem conectar a mesma usina Growatt física antes da
primeira coleta, porque a barreira ``_inverter_in_another_plant`` olha ``devices``
e o ``Device`` só nasce na coleta. Este módulo só **lê** e classifica; não
decifra credencial, não chama API de fabricante e nunca grava.

Nada do login, ``login_hint``, texto cifrado ou impressão digital sai daqui: as
consultas nem selecionam essas colunas. Os ``GW-PLANT-<id>`` são identificadores
de usina, não segredo.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.db_models import AuditEventRecord
from mplacas.db.models import Device, Plant
from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN
from mplacas.providers.db_models import ProviderAccountRecord

GROWATT_FAMILY = frozenset({GROWATT, GROWATT_TOKEN})
DEFAULT_SUSPECT_AFTER = timedelta(hours=48)

R1 = "R1"
R2 = "R2"
R3 = "R3"
R4 = "R4"
RULES = (R1, R2, R3, R4)
RULE_TITLES = {
    R1: "duplicata confirmada entre tipos de conexão",
    R2: "conexão que perdeu a disputa",
    R3: "suspeita (conectada sem aparelho)",
    R4: "para revisão (mais de um aparelho Growatt)",
}
# Gravado por cloud_jobs.run_collection (type(exc).__name__) quando a coleta
# recusa a usina; ver services/collection.py.
LOST_DISPUTE_FAILURE_CODE = "CollectionPlantError"
REFUSAL_ACTION = "provider_account.history_import_failed"
REFUSAL_REASON = "provider_inverter_in_another_plant"


@dataclass(frozen=True, slots=True)
class ClaimFinding:
    rule: str
    plant_id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    connected_at: datetime | None
    last_success_at: datetime | None
    last_failure_code: str | None
    serials: tuple[str, ...] = ()
    refusals_audited: int | None = None


@dataclass(frozen=True, slots=True)
class ClaimsReport:
    findings: tuple[ClaimFinding, ...]

    def count(self, rule: str) -> int:
        return sum(1 for finding in self.findings if finding.rule == rule)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _connected_at(record: ProviderAccountRecord) -> datetime | None:
    # Mesma noção do router: a mais recente entre criação e rotação.
    moments = [m for m in (_aware(record.created_at), _aware(record.rotated_at)) if m]
    return max(moments) if moments else None


async def build_claims_report(
    session: AsyncSession,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    suspect_after: timedelta = DEFAULT_SUSPECT_AFTER,
) -> ClaimsReport:
    """Lê (contexto de plataforma, definido por quem chama) e classifica."""
    moment = _aware(now())
    assert moment is not None

    plants = {
        row.id: row.organization_id
        for row in (await session.execute(select(Plant.id, Plant.organization_id))).all()
    }
    accounts = {
        record.plant_id: record
        for record in await session.scalars(
            select(ProviderAccountRecord).where(ProviderAccountRecord.active.is_(True))
        )
    }
    devices = (
        await session.execute(
            select(Device.plant_id, Device.provider, Device.serial_number).where(
                Device.provider.in_(sorted(GROWATT_FAMILY))
            )
        )
    ).all()

    by_plant: dict[uuid.UUID, list[tuple[str, str]]] = defaultdict(list)
    by_serial: dict[str, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    for plant_id, provider, serial in devices:
        by_plant[plant_id].append((provider, serial))
        by_serial[serial].append((plant_id, provider))

    def build(
        rule: str,
        plant_id: uuid.UUID,
        provider: str,
        serials: tuple[str, ...] = (),
        refusals: int | None = None,
    ) -> ClaimFinding:
        account = accounts.get(plant_id)
        return ClaimFinding(
            rule=rule,
            plant_id=plant_id,
            organization_id=plants[plant_id],
            provider=provider,
            connected_at=_connected_at(account) if account else None,
            last_success_at=_aware(account.last_success_at) if account else None,
            last_failure_code=account.last_failure_code if account else None,
            serials=serials,
            refusals_audited=refusals,
        )

    findings: list[ClaimFinding] = []

    # R1: mesmo serial, dois tipos de conexão, usinas diferentes.
    for serial in sorted(by_serial):
        holders = by_serial[serial]
        if len({provider for _, provider in holders}) < 2:
            continue
        if len({plant_id for plant_id, _ in holders}) < 2:
            continue
        for plant_id, provider in sorted(holders, key=lambda h: (str(h[0]), h[1])):
            if plant_id in plants:
                findings.append(build(R1, plant_id, provider, (serial,)))

    # R2: conexão ativa que perdeu a disputa na coleta (+ recusas auditadas).
    lost = {
        plant_id: record
        for plant_id, record in accounts.items()
        if record.last_failure_code == LOST_DISPUTE_FAILURE_CODE and plant_id in plants
    }
    refusals: dict[str, int] = defaultdict(int)
    if lost:
        events = await session.execute(
            select(AuditEventRecord.resource_id, AuditEventRecord.details).where(
                AuditEventRecord.action == REFUSAL_ACTION,
                AuditEventRecord.resource_type == "plant",
            )
        )
        for resource_id, details in events.all():
            if not (resource_id and isinstance(details, dict)):
                continue
            if details.get("reason") == REFUSAL_REASON:
                refusals[resource_id] += 1
    for plant_id, record in sorted(lost.items(), key=lambda item: str(item[0])):
        findings.append(
            build(R2, plant_id, record.provider, refusals=refusals.get(str(plant_id), 0))
        )

    # R3: conectada há mais que o limite e sem nenhum aparelho da família.
    for plant_id, record in sorted(accounts.items(), key=lambda item: str(item[0])):
        if record.provider not in GROWATT_FAMILY or plant_id not in plants:
            continue
        connected = _connected_at(record)
        if connected is None or moment - connected <= suspect_after:
            continue
        if by_plant.get(plant_id):
            continue
        findings.append(build(R3, plant_id, record.provider))

    # R4: mais de um aparelho da família na mesma usina.
    for plant_id in sorted(by_plant, key=str):
        rows = by_plant[plant_id]
        if len(rows) < 2 or plant_id not in plants:
            continue
        account = accounts.get(plant_id)
        provider = account.provider if account else "/".join(sorted({p for p, _ in rows}))
        findings.append(build(R4, plant_id, provider, tuple(sorted(s for _, s in rows))))

    return ClaimsReport(findings=tuple(findings))


def _fmt(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M") if moment else "-"


def render_claims_report(report: ClaimsReport, *, totals_only: bool = False) -> str:
    """Linhas legíveis em português, mais a contagem final por regra.

    ``totals_only``: só a contagem, sem usina, organização nem serial. É o que
    roda no GitHub Actions — o repositório é público e o log do job também.
    """
    lines = ["Relatório de reservas de usina Growatt (somente leitura)"]
    for rule in () if totals_only else RULES:
        lines.append(f"{rule} - {RULE_TITLES[rule]}")
        found = [f for f in report.findings if f.rule == rule]
        if not found:
            lines.append("  nenhum caso")
        for f in found:
            parts = [
                f"  {f.rule}",
                f"usina={f.plant_id}",
                f"organizacao={f.organization_id}",
                f"provedor={f.provider}",
                f"conectada_em={_fmt(f.connected_at)}",
                f"ultimo_sucesso={_fmt(f.last_success_at)}",
                f"ultima_falha={f.last_failure_code or '-'}",
            ]
            if f.serials:
                parts.append(f"serial={','.join(f.serials)}")
            if f.refusals_audited is not None:
                parts.append(f"recusas_auditadas={f.refusals_audited}")
            lines.append(" ".join(parts))
    lines.append("Total por regra: " + ", ".join(f"{r}={report.count(r)}" for r in RULES))
    return "\n".join(lines)
