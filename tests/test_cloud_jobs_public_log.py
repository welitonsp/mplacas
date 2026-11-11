"""O stderr dos jobs vai para o log público do GitHub Actions: nada de texto de terceiros."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError

import mplacas.cloud_jobs as cloud_jobs
from mplacas.cloud_jobs import OperatorError, main
from mplacas.core.config import get_settings

_URL_ORIGINAL = "postgres://usuario:s3nh4-s3cr3t4@db.interno.example:5432/mplacas"


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.setenv("MPLACAS_DATABASE_URL", _URL_ORIGINAL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _falhar_com(monkeypatch, exc: BaseException) -> None:
    def handler(_args) -> int:
        raise exc

    monkeypatch.setattr(cloud_jobs, "_handle_smoke", handler)


def test_conexao_recusada_imprime_so_a_classe(monkeypatch, capsys) -> None:
    _falhar_com(monkeypatch, ConnectionRefusedError("Connect call failed ('10.1.2.3', 5432)"))

    assert main(["smoke"]) == 1

    captured = capsys.readouterr()
    assert "ConnectionRefusedError" in captured.err
    assert "10.1.2.3" not in captured.err
    assert "5432" not in captured.err
    assert "request_id=job-" in captured.err
    assert captured.out == ""


def test_erro_do_sqlalchemy_nao_vaza_senha_nem_parametros(monkeypatch, capsys) -> None:
    exc = DBAPIError(
        "INSERT INTO provider_accounts (secret) VALUES ($1)",
        {"secret": "valor-cifrado-xyz", "senha": "hunter2-falsa"},
        Exception("senha hunter2-falsa rejeitada"),
    )
    _falhar_com(monkeypatch, exc)

    assert main(["smoke"]) == 1

    captured = capsys.readouterr()
    assert "DBAPIError" in captured.err
    for trecho in ("hunter2-falsa", "valor-cifrado-xyz", "INSERT", "provider_accounts"):
        assert trecho not in captured.err
    assert captured.out == ""


def test_mensagem_deliberada_do_operador_e_impressa(monkeypatch, capsys) -> None:
    _falhar_com(monkeypatch, OperatorError("collection failed for 1 plant(s): abc-123"))

    assert main(["smoke"]) == 1

    captured = capsys.readouterr()
    assert "error: collection failed for 1 plant(s): abc-123" in captured.err
    assert captured.out == ""


def test_mensagem_deliberada_com_url_do_banco_e_redigida(monkeypatch, capsys) -> None:
    normalizada = get_settings().database_url
    assert normalizada.startswith("postgresql+asyncpg://")
    _falhar_com(
        monkeypatch,
        OperatorError(
            f"falha em {normalizada} e em {_URL_ORIGINAL} com senha s3nh4-s3cr3t4"
        ),
    )

    assert main(["smoke"]) == 1

    err = capsys.readouterr().err
    for trecho in ("s3nh4-s3cr3t4", "db.interno.example", "usuario", "postgres://"):
        assert trecho not in err
    assert "<database-url>" in err or "<redacted>" in err


def test_falha_ao_carregar_configuracao_nomeia_campo_sem_valor(monkeypatch, capsys) -> None:
    class Modelo(BaseModel):
        database_url: int

    with pytest.raises(ValidationError) as info:
        Modelo(database_url="postgresql+asyncpg://u:abcd1234segredo@10.9.8.7:5432/mplacas")

    def quebrar():
        raise info.value

    monkeypatch.setattr(cloud_jobs, "get_settings", quebrar)

    assert main(["smoke"]) == 1

    captured = capsys.readouterr()
    assert "ValidationError" in captured.err
    assert "database_url" in captured.err
    for trecho in ("abcd1234segredo", "10.9.8.7", "postgresql", "input_value", "integer"):
        assert trecho not in captured.err
    assert captured.out == ""


def test_falha_de_configuracao_generica_imprime_so_a_classe(monkeypatch, capsys) -> None:
    def quebrar():
        raise OSError("nao consegui ler /segredos/10.1.2.3")

    monkeypatch.setattr(cloud_jobs, "get_settings", quebrar)

    assert main(["smoke"]) == 1

    err = capsys.readouterr().err
    assert "OSError" in err
    assert "10.1.2.3" not in err


def test_motivo_parcial_de_terceiros_vira_nome_da_classe() -> None:
    assert cloud_jobs._operator_reason(OperatorError("texto nosso")) == "texto nosso"
    assert cloud_jobs._operator_reason(OSError("10.1.2.3")) == "OSError"


def test_sanitize_nao_derruba_com_url_invalida() -> None:
    assert cloud_jobs._sanitize("msg", "http://[::1") == "msg"


def test_falha_de_migracao_mostra_so_o_tipo_do_erro() -> None:
    from mplacas.cloud_jobs import _migration_failure_summary

    stderr = (
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\n'
        "sqlalchemy.exc.ProgrammingError: (asyncpg.exceptions.DuplicateTableError) "
        'relation "provider_plant_claims" already exists [SQL: CREATE TABLE ...] '
        "host=10.1.2.3 password=segredo\n"
    )
    summary = _migration_failure_summary(stderr)
    assert summary == "migration failed: sqlalchemy.exc.ProgrammingError"
    assert "10.1.2.3" not in summary and "segredo" not in summary and "SQL" not in summary
    assert _migration_failure_summary("") == "migration failed"
    assert _migration_failure_summary("qualquer coisa sem tipo") == "migration failed"
