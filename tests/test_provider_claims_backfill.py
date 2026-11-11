"""Preenchimento das reservas de usina (ADR-100): só insere, idempotente, sem vazar serial."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from mplacas.cloud_jobs import _build_parser
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN, NEPVIEWER
from mplacas.providers.claims_report import (
    BACKFILL_PROVIDERS,
    ClaimsBackfillResult,
    backfill_claims,
    render_backfill,
)
from mplacas.providers.db_models import ProviderPlantClaimRecord

from test_provider_claims_report import (
    ORG_A,
    ORG_B,
    PLANT_A,
    PLANT_B,
    _account,
    _device,
    _factory,
    _seed,
)

PLANT_C = uuid.UUID("00000000-0000-0000-0000-00000000000c")


async def _run(factory) -> ClaimsBackfillResult:
    async with factory() as session:
        result = await backfill_claims(session)
        await session.commit()
    return result


async def _claims(factory) -> set[tuple[uuid.UUID, str, str]]:
    async with factory() as session:
        rows = await session.execute(
            select(
                ProviderPlantClaimRecord.plant_id,
                ProviderPlantClaimRecord.provider_family,
                ProviderPlantClaimRecord.serial_number,
            )
        )
        return {tuple(row) for row in rows.all()}


def _totals(result: ClaimsBackfillResult) -> tuple[int, int, int, int]:
    return (result.created, result.already_present, len(result.conflicts), result.ignored)


async def test_conexao_token_com_aparelho_sem_reserva_cria_uma_e_segunda_vez_nao_cria() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    assert _totals(await _run(factory)) == (1, 0, 0, 0)
    assert await _claims(factory) == {(PLANT_A, "GROWATT", "GW-PLANT-1")}
    assert _totals(await _run(factory)) == (0, 1, 0, 0)
    assert len(await _claims(factory)) == 1


async def test_conexao_por_senha_tambem_reserva_na_familia_growatt() -> None:
    factory = await _factory()
    await _seed(factory, _account(PLANT_A, GROWATT), _device(PLANT_A, GROWATT, "GW-PLANT-1"))
    assert _totals(await _run(factory)) == (1, 0, 0, 0)
    assert await _claims(factory) == {(PLANT_A, "GROWATT", "GW-PLANT-1")}


async def test_conexao_senha_reserva_aparelho_gravado_como_token_da_mesma_familia() -> None:
    factory = await _factory()
    await _seed(factory, _account(PLANT_A, GROWATT), _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"))
    assert _totals(await _run(factory)) == (1, 0, 0, 0)


async def test_nepviewer_reserva_com_a_propria_familia() -> None:
    # Device.serial_number da NEPViewer é o mesmo que a conferência entrega a
    # save(serials=...): ambos vêm de client.list_devices().
    assert NEPVIEWER in BACKFILL_PROVIDERS
    factory = await _factory()
    await _seed(factory, _account(PLANT_A, NEPVIEWER), _device(PLANT_A, NEPVIEWER, "NEP-SN-9"))
    assert _totals(await _run(factory)) == (1, 0, 0, 0)
    assert await _claims(factory) == {(PLANT_A, NEPVIEWER, "NEP-SN-9")}


async def test_marca_fora_da_lista_e_ignorada_e_contada() -> None:
    factory = await _factory()
    await _seed(factory, _account(PLANT_A, "OUTRA"), _device(PLANT_A, "OUTRA", "X-1"))
    assert _totals(await _run(factory)) == (0, 0, 0, 1)
    assert await _claims(factory) == set()


async def test_conexao_inativa_nao_grava_nada() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, GROWATT_TOKEN, active=False),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    assert _totals(await _run(factory)) == (0, 0, 0, 0)
    assert await _claims(factory) == set()


async def test_usina_com_aparelho_e_sem_conexao_nao_grava_nada() -> None:
    factory = await _factory()
    await _seed(factory, _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"))
    assert _totals(await _run(factory)) == (0, 0, 0, 0)
    assert await _claims(factory) == set()


async def test_aparelho_de_outra_familia_nao_e_reservado() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
        _device(PLANT_A, NEPVIEWER, "NEP-SN-9"),
    )
    assert _totals(await _run(factory)) == (1, 0, 0, 1)
    assert await _claims(factory) == {(PLANT_A, "GROWATT", "GW-PLANT-1")}


async def test_conflito_com_reserva_de_outra_usina_nao_grava_e_nao_derruba_as_demais() -> None:
    factory = await _factory()
    await _seed(
        factory,
        Plant(id=PLANT_C, organization_id=ORG_A, name="C"),
    )
    await _seed(
        factory,
        ProviderPlantClaimRecord(
            plant_id=PLANT_B, provider_family="GROWATT", serial_number="GW-PLANT-1"
        ),
        _account(PLANT_A, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
        _account(PLANT_C, GROWATT),
        _device(PLANT_C, GROWATT, "GW-PLANT-3"),
    )
    result = await _run(factory)
    assert _totals(result) == (1, 0, 1, 0)
    assert [(c.plant_id, c.serial_number) for c in result.conflicts] == [(PLANT_A, "GW-PLANT-1")]
    assert await _claims(factory) == {
        (PLANT_B, "GROWATT", "GW-PLANT-1"),
        (PLANT_C, "GROWATT", "GW-PLANT-3"),
    }


async def test_mesmo_serial_em_aparelhos_de_duas_usinas_nao_reserva_nenhuma_as_cegas() -> None:
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, GROWATT),
        _device(PLANT_A, GROWATT, "GW-PLANT-1"),
        _account(PLANT_B, GROWATT_TOKEN),
        _device(PLANT_B, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    result = await _run(factory)
    assert _totals(result) == (0, 0, 2, 0)
    assert await _claims(factory) == set()


async def test_corrida_unique_no_banco_vira_conflito_sem_levantar(monkeypatch) -> None:
    """A reserva aparece entre a leitura e o INSERT: o savepoint isola o IntegrityError."""
    factory = await _factory()
    await _seed(
        factory,
        _account(PLANT_A, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    async with factory() as other:
        other.add(
            ProviderPlantClaimRecord(
                plant_id=PLANT_B, provider_family="GROWATT", serial_number="GW-PLANT-1"
            )
        )
        await other.commit()

    async with factory() as session:
        real_execute = session.execute
        calls = {"n": 0}

        async def blind_to_claims(statement, *args, **kwargs):
            # Esconde as reservas só da leitura inicial, simulando a corrida.
            calls["n"] += 1
            result = await real_execute(statement, *args, **kwargs)
            if "provider_plant_claims" in str(statement) and "INSERT" not in str(statement):
                return type("Vazio", (), {"all": staticmethod(lambda: [])})()
            return result

        monkeypatch.setattr(session, "execute", blind_to_claims)
        result = await backfill_claims(session)
        await session.commit()
    assert _totals(result) == (0, 0, 1, 0)
    assert await _claims(factory) == {(PLANT_B, "GROWATT", "GW-PLANT-1")}


async def test_reserva_existente_nunca_e_apagada_nem_alterada() -> None:
    factory = await _factory()
    unrelated = ProviderPlantClaimRecord(
        plant_id=PLANT_B, provider_family="GROWATT", serial_number="GW-PLANT-77"
    )
    await _seed(
        factory,
        unrelated,
        _account(PLANT_A, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-1"),
    )
    await _run(factory)
    assert (PLANT_B, "GROWATT", "GW-PLANT-77") in await _claims(factory)
    async with factory() as session:
        row = await session.get(ProviderPlantClaimRecord, unrelated.id)
        assert row is not None
        assert (row.plant_id, row.provider_family, row.serial_number) == (
            PLANT_B,
            "GROWATT",
            "GW-PLANT-77",
        )


def test_parser_aceita_apply_e_apply_com_somente_totais() -> None:
    parser = _build_parser()
    assert parser.parse_args(["provider-claims-report"]).apply is False
    args = parser.parse_args(["provider-claims-report", "--apply"])
    assert args.apply is True and args.totals_only is False
    args = parser.parse_args(["provider-claims-report", "--apply", "--totals-only"])
    assert args.apply is True and args.totals_only is True


def test_render_somente_totais_nao_traz_usina_nem_serial() -> None:
    from mplacas.providers.claims_report import ClaimConflict

    result = ClaimsBackfillResult(
        created=1, conflicts=(ClaimConflict(PLANT_A, "GROWATT", "GW-PLANT-SEGREDO"),)
    )
    totals = render_backfill(result, totals_only=True)
    assert totals == "Reservas: criadas=1, ja_existiam=0, conflitos=1, ignoradas=0"
    detail = render_backfill(result)
    assert "GW-PLANT-SEGREDO" in detail and str(PLANT_A) in detail


async def _counts(factory) -> dict[str, int]:
    async with factory() as session:
        return {
            name: await session.scalar(select(func.count()).select_from(table))
            for name, table in Base.metadata.tables.items()
        }


async def test_sem_apply_nenhuma_tabela_muda_e_com_apply_a_saida_so_traz_totais(
    monkeypatch,
) -> None:
    import mplacas.cloud_jobs as cloud_jobs

    factory = await _factory()
    await _seed(
        factory,
        Plant(id=PLANT_C, organization_id=ORG_B, name="C"),
    )
    await _seed(
        factory,
        ProviderPlantClaimRecord(
            plant_id=PLANT_B, provider_family="GROWATT", serial_number="GW-PLANT-SEGREDO"
        ),
        _account(PLANT_A, GROWATT_TOKEN),
        _device(PLANT_A, GROWATT_TOKEN, "GW-PLANT-SEGREDO"),
        _account(PLANT_C, GROWATT),
        _device(PLANT_C, GROWATT, "GW-PLANT-3"),
    )
    monkeypatch.setattr(cloud_jobs, "SessionFactory", factory)

    before = await _counts(factory)
    dry = await cloud_jobs.run_provider_claims_report(totals_only=True)
    assert await _counts(factory) == before
    assert "Reservas:" not in dry

    applied = await cloud_jobs.run_provider_claims_report(totals_only=True, apply=True)
    assert applied.startswith("Reservas: criadas=1, ja_existiam=0, conflitos=1, ignoradas=0\n")
    assert "GW-PLANT-SEGREDO" not in applied and "GW-PLANT-3" not in applied
    after = await _counts(factory)
    assert after["provider_plant_claims"] == before["provider_plant_claims"] + 1
    assert {k: v for k, v in after.items() if k != "provider_plant_claims"} == {
        k: v for k, v in before.items() if k != "provider_plant_claims"
    }

    again = await cloud_jobs.run_provider_claims_report(totals_only=True, apply=True)
    assert again.startswith("Reservas: criadas=0, ja_existiam=1, conflitos=1, ignoradas=0\n")
