"""Regra da "usina agora" (ADR-099) sem rota, sem banco e sem rede."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from mplacas.providers.base import ProviderUnavailableError
from mplacas.providers.live_reading import (
    LIVE_FAILURE_TTL,
    LIVE_STALE_LIMIT,
    LIVE_TTL,
    BrandSnapshot,
    LiveReadingBrandDownError,
    LiveReadingCache,
    LiveReadingService,
    LiveReadingUnavailableError,
    NightTotal,
    own_values,
)

PLANT = uuid.uuid4()
ACCOUNT = uuid.uuid4()
START = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
ONE_PLANT = {"GW-PLANT-1": (Decimal("9215.4"), Decimal("2.3"))}


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class Brand:
    """Marca de mentira: conta as chamadas e pode falhar ou demorar."""

    def __init__(self, readings=ONE_PLANT, own=()) -> None:
        self.readings = readings
        self.own = frozenset(own)
        self.calls = 0
        self.fail = False
        self.gate: asyncio.Event | None = None

    async def load(self) -> BrandSnapshot:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise ProviderUnavailableError("down")
        return BrandSnapshot(readings=self.readings, own_serials=self.own)


async def _no_night() -> NightTotal | None:
    return None


def _read(service, brand, *, night=_no_night, account=ACCOUNT, connected_at=START):
    return service.read(
        plant_id=PLANT,
        account_id=account,
        provider="GROWATT_TOKEN",
        connected_at=connected_at,
        load=brand.load,
        night_total=night,
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(clock: Clock) -> LiveReadingService:
    return LiveReadingService(LiveReadingCache(), clock=clock)


async def test_good_reading_is_reused_until_it_expires(service, clock) -> None:
    brand = Brand()
    first = await _read(service, brand)
    clock.advance(LIVE_TTL - timedelta(seconds=1))
    assert await _read(service, brand) == first
    assert brand.calls == 1
    clock.advance(timedelta(seconds=2))
    await _read(service, brand)
    assert brand.calls == 2


async def test_simultaneous_requests_call_the_brand_once(service) -> None:
    brand = Brand()
    brand.gate = asyncio.Event()
    pending = [asyncio.create_task(_read(service, brand)) for _ in range(5)]
    await asyncio.sleep(0)
    brand.gate.set()
    results = await asyncio.gather(*pending)
    assert brand.calls == 1
    assert len({result.read_at for result in results}) == 1


async def test_another_connection_never_reuses_the_reading(service) -> None:
    brand = Brand()
    await _read(service, brand)
    await _read(service, brand, account=uuid.uuid4())
    assert brand.calls == 2


async def test_failure_serves_last_reading_as_stale_and_waits(service, clock) -> None:
    brand = Brand()
    good = await _read(service, brand)
    clock.advance(LIVE_TTL + timedelta(minutes=1))
    brand.fail = True
    stale = await _read(service, brand)
    assert stale.stale is True and stale.total_kwh == good.total_kwh
    await _read(service, brand)
    assert brand.calls == 2  # dentro da espera, não insiste na marca
    clock.advance(LIVE_FAILURE_TTL + timedelta(seconds=1))
    await _read(service, brand)
    assert brand.calls == 3


async def test_stale_reading_expires_after_a_day(service, clock) -> None:
    brand = Brand()
    await _read(service, brand)
    clock.advance(LIVE_STALE_LIMIT + timedelta(minutes=1))
    brand.fail = True
    with pytest.raises(LiveReadingBrandDownError):
        await _read(service, brand)


async def test_failure_without_memory_uses_the_night_total(service, clock) -> None:
    brand = Brand()
    brand.fail = True

    async def night() -> NightTotal | None:
        return NightTotal(Decimal("9200.0"), clock.now - timedelta(hours=10))

    reading = await _read(service, brand, night=night, connected_at=START - timedelta(days=3))
    assert reading.stale is True
    assert reading.total_kwh == Decimal("9200.0")
    assert reading.current_power_kw is None
    assert reading.read_at == clock.now - timedelta(hours=10)


@pytest.mark.parametrize(
    ("age", "connected_ago"),
    [
        (timedelta(hours=10), timedelta(hours=1)),  # gravado por uma conexão anterior
        (timedelta(hours=49), timedelta(days=5)),  # velho demais
    ],
)
async def test_night_total_is_refused_when_not_trustworthy(
    service, clock, age, connected_ago
) -> None:
    brand = Brand()
    brand.fail = True

    async def night() -> NightTotal | None:
        return NightTotal(Decimal("9200.0"), clock.now - age)

    with pytest.raises(LiveReadingBrandDownError):
        await _read(service, brand, night=night, connected_at=START - connected_ago)


async def test_missing_field_is_none_never_zero(service) -> None:
    brand = Brand(readings={"GW-PLANT-1": (Decimal("10"), None)})
    reading = await _read(service, brand)
    assert reading.total_kwh == Decimal("10")
    assert reading.current_power_kw is None


async def test_nothing_informed_is_unavailable(service) -> None:
    with pytest.raises(LiveReadingUnavailableError):
        await _read(service, Brand(readings={"GW-PLANT-1": (None, None)}))


def test_own_values_never_sums_plants_of_other_places() -> None:
    two = {
        "GW-PLANT-1": (Decimal("1"), Decimal("1")),
        "GW-PLANT-2": (Decimal("5"), Decimal("5")),
    }
    # sem aparelho ligado e token com duas usinas: falha fechada
    assert own_values(BrandSnapshot(two, frozenset())) == []
    assert own_values(BrandSnapshot(two, frozenset({"GW-PLANT-2"}))) == [two["GW-PLANT-2"]]
    assert own_values(BrandSnapshot(ONE_PLANT, frozenset())) == [ONE_PLANT["GW-PLANT-1"]]


def test_prune_drops_old_entries_and_idle_locks(clock) -> None:
    cache = LiveReadingCache()
    service = LiveReadingService(cache, clock=clock)
    asyncio.run(_read(service, Brand()))
    assert PLANT in cache.entries
    clock.advance(LIVE_TTL + LIVE_STALE_LIMIT + timedelta(seconds=1))
    cache.prune(clock.now)
    assert cache.entries == {} and cache._locks == {}
