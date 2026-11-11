"""Validação das configurações antes de qualquer módulo que as use ao ser importado.

``mplacas.db.session`` cria o engine no import (``get_settings()``). Se a configuração
for inválida, o pydantic levanta ``ValidationError`` com ``input_value=...`` num
traceback — e o stderr dos jobs (GitHub Actions) é público. Este módulo é leve
(só ``core.config``) e é chamado por ``python -m mplacas.cloud_jobs`` antes dos
imports pesados, para trocar esse traceback por uma linha segura.
"""

from __future__ import annotations

import sys

from pydantic import ValidationError

from mplacas.core.config import get_settings


def validation_error_summary(exc: ValidationError) -> str:
    """Só os nomes dos campos: input/msg podem trazer fragmentos da URL do banco."""
    fields = sorted({".".join(str(part) for part in err["loc"]) for err in exc.errors()})
    fields = [name for name in fields if name]
    if not fields:
        # Regra que cruza vários campos (ex.: obrigatórios em produção): sem nome.
        return f"{type(exc).__name__} (invalid configuration)"
    return f"{type(exc).__name__} (invalid fields: {', '.join(fields)})"


def ensure_valid_settings() -> None:
    """Sai com código 1 e uma linha segura se a configuração for inválida."""
    try:
        get_settings()
        # Cria o engine aqui dentro: uma URL que o pydantic aceita mas o
        # SQLAlchemy não entende (porta inválida) estouraria no import seguinte,
        # com traceback e um pedaço da URL.
        import mplacas.db.session  # noqa: F401, PLC0415
    except ValidationError as exc:
        print(f"error: {validation_error_summary(exc)}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:  # noqa: BLE001 - nunca mostrar texto de terceiros
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
