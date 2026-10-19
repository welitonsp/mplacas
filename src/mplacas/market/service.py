"""Leitura de taxas mensais com reabastecimento sob demanda no Banco Central.

Os meses já guardados no banco são usados direto. Faltando meses já
fechados, busca no BCB (no máximo uma tentativa a cada 6 horas por
indicador e processo, para não insistir quando a API estiver fora) e grava.
Se o host do BCB não estiver em ``MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS`` ou a
busca falhar, devolve o que houver no banco — quem chama decide o que fazer
com meses ausentes (o painel do investidor marca "indisponível").
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.market.bcb import SOURCE, BcbSgsClient, BcbSgsError
from mplacas.market.db_models import MarketIndexMonthlyRecord

logger = logging.getLogger(__name__)

_RETRY_INTERVAL_SECONDS = 6 * 3600
_last_attempt: dict[str, float] = {}


def month_range(start_month: str, end_month: str) -> list[str]:
    """Meses "AAAA-MM" de ``start_month`` a ``end_month``, inclusive."""
    year, month = (int(part) for part in start_month.split("-"))
    end_year, end_m = (int(part) for part in end_month.split("-"))
    months: list[str] = []
    while (year, month) <= (end_year, end_m):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def last_closed_month(today: date) -> str:
    year, month = today.year, today.month - 1
    if month == 0:
        year, month = year - 1, 12
    return f"{year:04d}-{month:02d}"


def bcb_host_allowed(base_url: str, allowed_hosts: frozenset[str]) -> bool:
    """Só HTTPS e só host liberado na allowlist de saída."""
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and bool(host) and host in allowed_hosts


async def monthly_rates(
    session: AsyncSession,
    index_code: str,
    *,
    start_month: str,
    end_month: str,
    client: BcbSgsClient | None,
    today: date,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Decimal]:
    """Taxas de ``index_code`` (% ao mês) por mês, de ``start_month`` até
    o menor entre ``end_month`` e o último mês fechado.

    ``client=None`` = não buscar fora (host não liberado ou teste): só o banco.
    """
    upper = min(end_month, last_closed_month(today))
    wanted = month_range(start_month, upper) if start_month <= upper else []
    stored = await _stored(session, index_code, wanted)
    missing = [month for month in wanted if month not in stored]
    if not missing or client is None:
        return stored

    now = clock()
    last = _last_attempt.get(index_code)
    if last is not None and now - last < _RETRY_INTERVAL_SECONDS:
        return stored
    _last_attempt[index_code] = now

    first_year, first_month = (int(part) for part in missing[0].split("-"))
    last_year, last_month = (int(part) for part in missing[-1].split("-"))
    try:
        fetched = await client.monthly_rates(
            index_code,
            start=date(first_year, first_month, 1),
            end=date(last_year, last_month, 28),
        )
    except BcbSgsError:
        logger.warning("market_index_fetch_failed", extra={"index_code": index_code})
        return stored

    # Só os meses pedidos e ainda ausentes, sem repetição: o BCB não tem por
    # que devolver outro mês, e se devolver não é gravado. Mês fechado não
    # muda depois de publicado, então o que já está no banco não é
    # sobrescrito.
    missing_set = set(missing)
    new_rates: dict[str, Decimal] = {}
    for rate in fetched:
        if rate.reference_month in missing_set:
            new_rates.setdefault(rate.reference_month, rate.rate_percent)
    if not new_rates:
        return stored
    try:
        # Savepoint: outra requisição (ou outro worker) pode ter gravado o
        # mesmo mês no meio do caminho. A violação da unicidade desfaz só
        # este bloco, e a leitura do usuário segue com o que está no banco.
        async with session.begin_nested():
            session.add_all(
                MarketIndexMonthlyRecord(
                    index_code=index_code,
                    reference_month=month,
                    rate_percent=value,
                    source=SOURCE,
                )
                for month, value in sorted(new_rates.items())
            )
    except IntegrityError:
        logger.info("market_index_concurrent_insert", extra={"index_code": index_code})
        return await _stored(session, index_code, wanted)
    stored.update(new_rates)
    return stored


async def _stored(session: AsyncSession, index_code: str, months: list[str]) -> dict[str, Decimal]:
    if not months:
        return {}
    rows = (
        await session.scalars(
            select(MarketIndexMonthlyRecord).where(
                MarketIndexMonthlyRecord.index_code == index_code,
                MarketIndexMonthlyRecord.reference_month >= months[0],
                MarketIndexMonthlyRecord.reference_month <= months[-1],
            )
        )
    ).all()
    return {row.reference_month: Decimal(row.rate_percent) for row in rows}
