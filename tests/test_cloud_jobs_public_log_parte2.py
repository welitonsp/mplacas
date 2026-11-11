"""Parte 2 do log público dos jobs: traceback, import com config inválida, nomes e ::."""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import mplacas.cloud_jobs as cloud_jobs
from mplacas.core.config import get_settings
from mplacas.observability.logging import configure_logging
from mplacas.orchestration.db_models import PipelineExecutionStatus

_RAIZ = Path(__file__).resolve().parents[1]
_SEGREDOS = ("db.interno.example", "s3nh4-s3cr3t4", "INSERT INTO", "DETAIL: chave")


@pytest.fixture
def _log_raiz_limpo(monkeypatch):
    """Entrega função que esvazia o root *no corpo do teste*.

    O plugin de logging do pytest reanexa seus handlers a cada fase, então esvaziar
    só no setup não basta para o ``basicConfig`` de ``configure_logging`` valer.
    """
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level

    def esvaziar() -> None:
        root.handlers = []

    yield esvaziar
    root.handlers, root.level = handlers, level


def _emitir_excecao(monkeypatch, esvaziar, *, public: bool, structured: bool) -> str:
    saida = io.StringIO()
    monkeypatch.setattr(sys, "stdout", saida)
    esvaziar()
    configure_logging(level="INFO", service_name="teste", structured=structured, public=public)
    try:
        try:
            raise ConnectionRefusedError("connect to db.interno.example:5432 senha s3nh4-s3cr3t4")
        except ConnectionRefusedError as inner:
            raise RuntimeError(
                "INSERT INTO t VALUES ('x') DETAIL: chave (id)=(7) host db.interno.example"
            ) from inner
    except RuntimeError:
        logging.getLogger("mplacas.teste").exception("operacao_falhou")
    return saida.getvalue()


@pytest.mark.parametrize("structured", [True, False])
def test_log_de_job_emite_so_as_classes_da_excecao(
    monkeypatch, _log_raiz_limpo, structured
) -> None:
    linha = _emitir_excecao(monkeypatch, _log_raiz_limpo, public=True, structured=structured)

    assert "RuntimeError" in linha
    assert "ConnectionRefusedError" in linha
    assert "Traceback" not in linha
    for trecho in _SEGREDOS:
        assert trecho not in linha
    if structured:
        assert json.loads(linha)["message"] == "operacao_falhou"


def test_log_da_api_mantem_o_traceback_completo(monkeypatch, _log_raiz_limpo) -> None:
    linha = _emitir_excecao(monkeypatch, _log_raiz_limpo, public=False, structured=True)

    assert "Traceback" in json.loads(linha)["exception"]
    assert "INSERT INTO" in linha


def test_log_de_job_cobre_registro_com_exc_info_e_causa_por_contexto(
    monkeypatch, _log_raiz_limpo
) -> None:
    saida = io.StringIO()
    monkeypatch.setattr(sys, "stdout", saida)
    _log_raiz_limpo()
    configure_logging(level="INFO", service_name="t", structured=True, public=True)
    try:
        try:
            raise OSError("segredo-contexto")
        except OSError:
            raise ValueError("segredo-valor")  # noqa: B904 - exercita __context__
    except ValueError:
        logging.getLogger("x").warning("aviso", exc_info=True)
    linha = saida.getvalue()
    assert "ValueError" in linha and "OSError" in linha
    assert "segredo" not in linha


def test_entrypoint_com_config_invalida_imprime_so_o_campo() -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(_RAIZ / "src"),
        "MPLACAS_DATABASE_URL": "postgresql+asyncpg://usuario:s3nh4-s3cr3t4@db.interno.example/m",
        "MPLACAS_REQUEST_TIMEOUT_SECONDS": "valor-invalido-xyz",
    }
    result = subprocess.run(
        [sys.executable, "-m", "mplacas.cloud_jobs", "smoke"],
        cwd=str(_RAIZ),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    saida = result.stdout + result.stderr
    assert result.returncode == 1, saida
    assert "request_timeout_seconds" in saida
    assert "Traceback" not in saida
    for trecho in ("s3nh4-s3cr3t4", "db.interno.example", "usuario", "valor-invalido-xyz"):
        assert trecho not in saida
    assert len(result.stderr.strip().splitlines()) == 1


@pytest.fixture
def _env_url(monkeypatch):
    monkeypatch.setenv("MPLACAS_DATABASE_URL", "postgres://u:p@db.interno.example:5432/m")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _sem_clientes():
    return []


_NOME = "Maria da Silva Rua das Flores 123"


def test_vigia_nao_mostra_o_nome_da_usina(monkeypatch, _env_url) -> None:
    from test_cloud_jobs import FakeSession  # reaproveita o dublê de sessão

    plant = uuid.UUID("00000000-0000-0000-0000-0000000000f6")
    now = datetime(2026, 8, 2, 12, tzinfo=UTC)

    async def plantas(_org):
        return [(plant, _NOME)]

    async def ultimo(_session, *, plant_id):
        return SimpleNamespace(
            execution_id=uuid.uuid4(),
            status=PipelineExecutionStatus.FAILED,
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=1),
        )

    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", plantas)
    monkeypatch.setattr(cloud_jobs, "_list_connected_client_plants", _sem_clientes)
    monkeypatch.setattr(cloud_jobs, "get_latest_pipeline_execution", ultimo)
    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())

    with pytest.raises(cloud_jobs.OperatorError) as info:
        cloud_jobs.asyncio.run(cloud_jobs.run_operational_watchdog(now=now))
    assert str(plant) in str(info.value)
    assert "Maria" not in str(info.value) and "Flores" not in str(info.value)


def test_pipeline_diario_nao_mostra_o_nome_da_usina(monkeypatch, _env_url, caplog) -> None:
    from test_cloud_jobs import FakeSession, _set_daily_pipeline_env

    plant = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
    _set_daily_pipeline_env(monkeypatch)

    async def runtime(*_a, **_k):
        raise RuntimeError("texto de terceiros")

    async def plantas(_org):
        return [(plant, _NOME)]

    async def resolver(_session, *, plant_id, today):
        return SimpleNamespace(expected=None, unavailable_reason="sem baseline")

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", runtime)
    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", plantas)
    monkeypatch.setattr(cloud_jobs, "_list_connected_client_plants", _sem_clientes)
    monkeypatch.setattr(cloud_jobs, "resolve_expected_daily_production", resolver)

    with caplog.at_level(logging.INFO), pytest.raises(cloud_jobs.OperatorError) as info:
        cloud_jobs.asyncio.run(
            cloud_jobs.run_daily_pipeline(
                target_date="2026-07-15", now=datetime(2026, 7, 16, 3, 30, tzinfo=UTC)
            )
        )
    assert str(plant) in str(info.value)
    assert "Maria" not in str(info.value)
    assert "texto de terceiros" not in str(info.value)
    for registro in caplog.records:
        assert _NOME not in str(registro.__dict__)


def test_motivo_de_linha_ignorada_da_aneel_sai_em_uma_linha(monkeypatch, capsys) -> None:
    import argparse
    import contextlib
    from datetime import date

    import httpx

    import mplacas.tariffs.aneel_import as aneel

    periodo = SimpleNamespace(
        distributor="EQUATORIAL_GO",
        tariff_class="B1_RESIDENCIAL_CONVENCIONAL",
        valid_from=date(2025, 1, 1),
        valid_to=date(2025, 12, 31),
        full_brl_kwh="1",
        scee_brl_kwh="1",
        source="fonte\n::error::y",
    )
    parsed = SimpleNamespace(periods=[periodo], skipped=["linha ruim\n::add-mask::x"])

    class Resposta:
        def raise_for_status(self) -> None: ...

        def iter_bytes(self):
            return iter([b"a;b\n"])

    monkeypatch.setattr(
        httpx, "stream", lambda *a, **k: contextlib.nullcontext(Resposta())
    )
    monkeypatch.setattr(aneel, "read_csv", lambda _t: [])
    monkeypatch.setattr(aneel, "parse_aneel", lambda _r: parsed)

    with pytest.raises(aneel.AneelImportError):  # sanidade pós-impressão
        cloud_jobs._import_tariffs(
            argparse.Namespace(url="http://x", no_db=True, dry_run=True)
        )

    linhas = capsys.readouterr().out.splitlines()
    aviso = [linha for linha in linhas if "linha ruim" in linha]
    assert len(aviso) == 1
    assert "add-mask" in aviso[0] and "::" not in aviso[0]
    assert not any(linha.startswith("::") for linha in linhas)
