from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import mplacas.market.service as market_service
from mplacas.db.base import Base
from mplacas.market.bcb import BcbSgsClient, BcbSgsError, MonthlyRate, parse_monthly_payload
from mplacas.market.db_models import MarketIndexMonthlyRecord
from mplacas.market.service import bcb_host_allowed, last_closed_month, month_range, monthly_rates


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    market_service._last_attempt.clear()
    async with factory() as active:
        yield active
    await engine.dispose()


class FakeClient:
    def __init__(self, rates: list[MonthlyRate] | None = None, error: bool = False) -> None:
        self.rates = rates or []
        self.error = error
        self.calls: list[tuple[str, date, date]] = []

    async def monthly_rates(self, index_code: str, *, start: date, end: date):
        self.calls.append((index_code, start, end))
        if self.error:
            raise BcbSgsError("down")
        return tuple(self.rates)


def test_parse_bcb_payload() -> None:
    rates = parse_monthly_payload([{"data": "01/09/2026", "valor": "1.08"}])
    assert rates == (MonthlyRate(reference_month="2026-09", rate_percent=Decimal("1.08")),)


@pytest.mark.parametrize(
    "payload",
    [
        {"data": "01/09/2026"},
        [{"data": "2026-09-01", "valor": "1.0"}],
        [{"data": "01/09/2026", "valor": "abc"}],
        [{"data": "01/09/2026", "valor": "48.69"}],  # fora da faixa mensal plausível
    ],
)
def test_parse_bcb_payload_rejects_malformed(payload) -> None:
    with pytest.raises(BcbSgsError):
        parse_monthly_payload(payload)


def test_helpers() -> None:
    assert month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert last_closed_month(date(2026, 1, 10)) == "2025-12"
    allowed = frozenset({"api.bcb.gov.br"})
    assert bcb_host_allowed("https://api.bcb.gov.br", allowed)
    assert not bcb_host_allowed("https://api.bcb.gov.br", frozenset({"api.nepviewer.net"}))


async def test_fetches_missing_closed_months_and_stores_them(session) -> None:
    client = FakeClient(
        [MonthlyRate("2026-08", Decimal("1.16")), MonthlyRate("2026-09", Decimal("1.08"))]
    )
    rates = await monthly_rates(
        session,
        "CDI",
        start_month="2026-08",
        end_month="2026-10",  # outubro ainda aberto: não é pedido
        client=client,  # type: ignore[arg-type]
        today=date(2026, 10, 19),
    )
    assert rates == {"2026-08": Decimal("1.16"), "2026-09": Decimal("1.08")}
    stored = (await session.scalars(select(MarketIndexMonthlyRecord))).all()
    assert {(r.reference_month, r.rate_percent) for r in stored} == {
        ("2026-08", Decimal("1.16")),
        ("2026-09", Decimal("1.08")),
    }
    assert client.calls[0][1] == date(2026, 8, 1)


async def test_uses_the_database_without_calling_the_bank_when_complete(session) -> None:
    session.add(
        MarketIndexMonthlyRecord(
            index_code="CDI", reference_month="2026-09", rate_percent=Decimal("1.08"), source="X"
        )
    )
    await session.flush()
    client = FakeClient()
    rates = await monthly_rates(
        session,
        "CDI",
        start_month="2026-09",
        end_month="2026-09",
        client=client,  # type: ignore[arg-type]
        today=date(2026, 10, 19),
    )
    assert rates == {"2026-09": Decimal("1.08")}
    assert client.calls == []


async def test_bank_failure_returns_what_is_stored_and_throttles_retries(session) -> None:
    client = FakeClient(error=True)
    kwargs = dict(start_month="2026-08", end_month="2026-09", today=date(2026, 10, 19))
    first = await monthly_rates(session, "CDI", client=client, clock=lambda: 1000.0, **kwargs)  # type: ignore[arg-type]
    second = await monthly_rates(session, "CDI", client=client, clock=lambda: 1060.0, **kwargs)  # type: ignore[arg-type]
    assert first == {} and second == {}
    assert len(client.calls) == 1  # segunda tentativa dentro de 6 h não chama o BCB


async def test_without_client_only_reads_the_database(session) -> None:
    rates = await monthly_rates(
        session,
        "IPCA",
        start_month="2026-01",
        end_month="2026-09",
        client=None,
        today=date(2026, 10, 19),
    )
    assert rates == {}


async def test_http_client_builds_the_sgs_url_and_parses() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"data": "01/09/2026", "valor": "0.48"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = BcbSgsClient(client=http)
        rates = await client.monthly_rates("IPCA", start=date(2026, 9, 1), end=date(2026, 9, 28))
    assert "bcdata.sgs.433/dados" in str(seen["url"])
    assert "dataInicial=01%2F09%2F2026" in str(seen["url"])
    assert rates[0].rate_percent == Decimal("0.48")


async def test_http_error_status_becomes_domain_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(406))
    ) as http:
        with pytest.raises(BcbSgsError):
            await BcbSgsClient(client=http).monthly_rates(
                "CDI", start=date(2026, 1, 1), end=date(2026, 9, 28)
            )
