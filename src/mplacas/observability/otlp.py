"""Carregamento tolerante do exportador OTLP (extra opcional `mplacas[otlp]`).

O exportador não entra em `requirements.lock` nem na imagem de produção: o
projeto roda sem backend de observabilidade por decisão de custo (ADR-076).

Como `Settings` aceita `tracing_enabled`/`metrics_enabled` como configuração
válida desde que `MPLACAS_OTLP_ENDPOINT` esteja presente, é possível ligar o
recurso sem o pacote instalado. Isso não pode derrubar a aplicação — num
serviço com escala a zero, um `ModuleNotFoundError` no boot vira loop de
reinício e leva junto a função do produto por causa de um acessório.
"""
from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

logger = logging.getLogger(__name__)


def build_otlp_exporter(
    *,
    module: str,
    attribute: str,
    endpoint: str,
    signal: str,
) -> Any | None:
    """Instancia o exportador OTLP, ou devolve ``None`` registrando o motivo.

    Devolver ``None`` significa "siga sem exportar este sinal". O chamador nunca
    deve propagar a falha: a ausência do extra é uma condição de configuração,
    não um defeito de execução.
    """
    try:
        exporter_class = getattr(import_module(module), attribute)
    except (ImportError, AttributeError):
        logger.error(
            "otlp_exporter_unavailable",
            extra={
                "signal": signal,
                "remediation": (
                    "instale o extra opcional com `pip install mplacas[otlp]` ou "
                    f"desligue o sinal removendo MPLACAS_{signal.upper()}_ENABLED"
                ),
            },
        )
        return None
    return exporter_class(endpoint=endpoint)
