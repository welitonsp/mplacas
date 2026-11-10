"""A usina agora: leitura ao vivo na marca, com memória curta (ADR-099).

Regra de negócio isolada da rota HTTP e do banco: quem chama entrega duas
funções (``load`` lê a marca, ``night_total`` busca o último total gravado à
noite) e recebe uma ``LiveReading`` ou uma das duas exceções deste módulo.
Relógio e memória são injetados, então tudo aqui é testável sem rede, sem
banco e sem esperar o tempo passar.

A marca limita a frequência de leitura (Growatt 10012). Por isso:

- uma leitura boa vale ``LIVE_TTL``;
- depois de uma falha, espera ``LIVE_FAILURE_TTL`` antes de insistir;
- pedidos simultâneos da mesma usina fazem **uma** chamada à marca (os outros
  esperam e reaproveitam o resultado).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from mplacas.providers.base import ProviderError

LIVE_TTL = timedelta(minutes=10)
LIVE_FAILURE_TTL = timedelta(minutes=2)
# Leitura em memória só substitui um erro até esta idade.
LIVE_STALE_LIMIT = timedelta(hours=24)
# O total gravado à noite é de um dia fechado: vale por mais tempo.
NIGHT_TOTAL_LIMIT = LIVE_STALE_LIMIT * 2

# número de série da usina na marca → (kWh desde a instalação, kW agora)
BrandReadings = Mapping[str, tuple[Decimal | None, Decimal | None]]


class LiveReadingUnavailableError(Exception):
    """Esta usina não tem leitura ao vivo (a tela some)."""


class LiveReadingBrandDownError(Exception):
    """A marca falhou e não há leitura recente para mostrar no lugar."""


@dataclass(frozen=True, slots=True)
class LiveReading:
    provider: str
    # None = a marca não informou (nunca zero)
    total_kwh: Decimal | None
    current_power_kw: Decimal | None
    read_at: datetime
    # True: a marca falhou agora e esta é a última leitura boa
    stale: bool = False


@dataclass(frozen=True, slots=True)
class BrandSnapshot:
    """O que a marca respondeu e quais usinas dela pertencem a esta usina."""

    readings: BrandReadings
    own_serials: frozenset[str]


@dataclass(frozen=True, slots=True)
class NightTotal:
    total_kwh: Decimal
    read_at: datetime


@dataclass(slots=True)
class LiveEntry:
    account_id: uuid.UUID
    fresh_until: datetime
    result: LiveReading | None = None
    retry_after: datetime | None = None


class LiveReadingCache:
    """Memória do processo (instância única no Render), uma entrada por usina."""

    def __init__(self) -> None:
        self.entries: dict[uuid.UUID, LiveEntry] = {}
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}

    def lock(self, plant_id: uuid.UUID) -> asyncio.Lock:
        return self._locks.setdefault(plant_id, asyncio.Lock())

    def forget(self, plant_id: uuid.UUID) -> None:
        """A conexão mudou ou saiu: a leitura guardada não vale mais."""
        self.entries.pop(plant_id, None)

    def prune(self, now: datetime) -> None:
        expired = [
            plant_id
            for plant_id, entry in self.entries.items()
            if entry.fresh_until + LIVE_STALE_LIMIT < now
        ]
        for plant_id in expired:
            del self.entries[plant_id]
            lock = self._locks.get(plant_id)
            # Trava em uso fica: apagar criaria uma segunda para a mesma usina.
            if lock is not None and not lock.locked():
                del self._locks[plant_id]


def aware(moment: datetime) -> datetime:
    """SQLite devolve datas sem fuso; o PostgreSQL, com. Tudo em UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def own_values(snapshot: BrandSnapshot) -> list[tuple[Decimal | None, Decimal | None]]:
    """Só o que é desta usina: um token pode enxergar usinas de outros lugares.

    Sem aparelho ligado ainda, só é seguro se o token enxerga uma usina só;
    com mais de uma, falha fechada (lista vazia) em vez de somar a do vizinho.
    """
    if snapshot.own_serials:
        return [
            value
            for serial, value in snapshot.readings.items()
            if serial in snapshot.own_serials
        ]
    if len(snapshot.readings) == 1:
        return list(snapshot.readings.values())
    return []


class LiveReadingService:
    def __init__(
        self,
        cache: LiveReadingCache,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._cache = cache
        self._clock = clock

    async def read(
        self,
        *,
        plant_id: uuid.UUID,
        account_id: uuid.UUID,
        provider: str,
        connected_at: datetime,
        load: Callable[[], Awaitable[BrandSnapshot]],
        night_total: Callable[[], Awaitable[NightTotal | None]],
    ) -> LiveReading:
        self._cache.prune(self._clock())
        # Uma chamada à marca por usina de cada vez: quem chega junto espera e
        # sai pela memória, sem gastar a cota (10012).
        async with self._cache.lock(plant_id):
            now = self._clock()
            entry = self._cache.entries.get(plant_id)
            if entry is not None and entry.account_id != account_id:
                entry = None  # outra conexão
            if entry is not None and entry.result is not None and entry.fresh_until > now:
                return entry.result
            if entry is not None and entry.retry_after is not None and entry.retry_after > now:
                return await self._stale_or_fail(entry, now, provider, connected_at, night_total)
            try:
                snapshot = await load()
            except ProviderError:
                failed = entry or LiveEntry(account_id=account_id, fresh_until=now)
                failed.retry_after = now + LIVE_FAILURE_TTL
                self._cache.entries[plant_id] = failed
                return await self._stale_or_fail(failed, now, provider, connected_at, night_total)
            mine = own_values(snapshot)
            totals = [total for total, _ in mine if total is not None]
            powers = [power for _, power in mine if power is not None]
            if not totals and not powers:
                raise LiveReadingUnavailableError
            result = LiveReading(
                provider=provider,
                total_kwh=sum(totals, Decimal(0)) if totals else None,
                current_power_kw=sum(powers, Decimal(0)) if powers else None,
                read_at=now,
            )
            self._cache.entries[plant_id] = LiveEntry(
                account_id=account_id, fresh_until=now + LIVE_TTL, result=result
            )
            return result

    async def _stale_or_fail(
        self,
        entry: LiveEntry,
        now: datetime,
        provider: str,
        connected_at: datetime,
        night_total: Callable[[], Awaitable[NightTotal | None]],
    ) -> LiveReading:
        if entry.result is not None and entry.result.read_at + LIVE_STALE_LIMIT > now:
            return replace(entry.result, stale=True)
        # Sem leitura em memória (o Render reinicia a instância): o último total
        # gravado à noite (ADR-098) por esta mesma conexão ainda informa, com a
        # hora dele.
        night = await night_total()
        if (
            night is not None
            and night.read_at >= connected_at
            and night.read_at + NIGHT_TOTAL_LIMIT > now
        ):
            return LiveReading(
                provider=provider,
                total_kwh=night.total_kwh,
                current_power_kw=None,
                read_at=night.read_at,
                stale=True,
            )
        raise LiveReadingBrandDownError
