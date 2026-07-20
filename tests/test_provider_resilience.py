from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderAuthError,
    ProviderIncompleteDataError,
    ProviderSchemaError,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)
from mplacas.providers.nepviewer.client import NepViewerClient
from mplacas.providers.resilient import ResilientSolarProvider, RetryPolicy


class ScriptedProvider(SolarProvider):
    """Provedor de teste que segue um roteiro de respostas/erros por chamada."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def list_devices(self) -> list[SolarDevice]:
        return self._next()

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        return self._next()

    async def get_daily_energy(
        self,
        serial_number: str,
        start: date,
        end: date,
        *,
        expect_complete: bool = False,
    ) -> list[DailyEnergy]:
        return self._next()

    def _next(self):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_retry_recovers_after_transient_unavailability() -> None:
    rows = [DailyEnergy(production_date=date(2026, 7, 19), energy_kwh=Decimal("12.5"))]
    inner = ScriptedProvider(
        [ProviderUnavailableError("timeout"), ProviderUnavailableError("timeout"), rows]
    )
    provider = ResilientSolarProvider(
        inner,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        sleep=_no_sleep,
    )

    result = await provider.get_daily_energy("SN1", date(2026, 7, 19), date(2026, 7, 19))

    assert result == rows
    assert inner.calls == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_reraises_original_error() -> None:
    inner = ScriptedProvider([ProviderUnavailableError("down")] * 3)
    provider = ResilientSolarProvider(
        inner,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        sleep=_no_sleep,
    )

    with pytest.raises(ProviderUnavailableError):
        await provider.list_devices()
    assert inner.calls == 3


@pytest.mark.asyncio
async def test_retry_recovers_after_incomplete_data() -> None:
    rows = [DailyEnergy(production_date=date(2026, 7, 19), energy_kwh=Decimal("9.0"))]
    inner = ScriptedProvider([ProviderIncompleteDataError("missing day"), rows])
    provider = ResilientSolarProvider(
        inner,
        policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0),
        sleep=_no_sleep,
    )

    result = await provider.get_daily_energy("SN1", date(2026, 7, 19), date(2026, 7, 19))
    assert result == rows
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_auth_and_schema_errors_are_not_retried() -> None:
    for error in (ProviderAuthError("bad creds"), ProviderSchemaError("bad shape")):
        inner = ScriptedProvider([error])
        provider = ResilientSolarProvider(
            inner,
            policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
            sleep=_no_sleep,
        )
        with pytest.raises(type(error)):
            await provider.list_devices()
        assert inner.calls == 1


def test_retry_policy_validates_parameters() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="base_delay"):
        RetryPolicy(base_delay_seconds=-1)
    with pytest.raises(ValueError, match="backoff_multiplier"):
        RetryPolicy(backoff_multiplier=0.5)


def test_retry_policy_backoff_is_capped() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, backoff_multiplier=2.0)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 2.0
    assert policy.delay_for(10) == 30.0  # teto


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_client_flags_missing_day_when_completeness_expected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign-in"):
            return httpx.Response(200, json={"data": {"tokenInfo": {"token": "t"}}})
        # série que NÃO cobre o dia solicitado (2026-07-19)
        return httpx.Response(
            200,
            json={
                "data": {
                    "xAxisData": ["18/07/2026 00:00:00"],
                    "series": [{"data": [10.0]}],
                }
            },
        )

    client = NepViewerClient(
        account="a",
        password="p",
        base_url="https://example.test/v2",
        transport=_transport(handler),
    )
    try:
        with pytest.raises(ProviderIncompleteDataError):
            await client.get_daily_energy(
                "SN1", date(2026, 7, 19), date(2026, 7, 19), expect_complete=True
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_client_timeout_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign-in"):
            return httpx.Response(200, json={"data": {"tokenInfo": {"token": "t"}}})
        raise httpx.TimeoutException("slow", request=request)

    client = NepViewerClient(
        account="a",
        password="p",
        base_url="https://example.test/v2",
        transport=_transport(handler),
    )
    try:
        with pytest.raises(ProviderUnavailableError):
            await client.get_daily_energy("SN1", date(2026, 7, 19), date(2026, 7, 20))
    finally:
        await client.aclose()



@pytest.mark.asyncio
async def test_factory_wraps_client_with_resilience() -> None:
    from mplacas.providers.nepviewer.factory import build_resilient_nepviewer

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign-in"):
            return httpx.Response(200, json={"data": {"tokenInfo": {"token": "t"}}})
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.TimeoutException("slow", request=request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "xAxisData": ["19/07/2026 00:00:00"],
                    "series": [{"data": [15.0]}],
                }
            },
        )

    client, provider = build_resilient_nepviewer(
        account="a",
        password="p",
        base_url="https://example.test/v2",
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        transport=httpx.MockTransport(handler),
    )
    try:
        rows = await provider.get_daily_energy(
            "SN1", date(2026, 7, 19), date(2026, 7, 20)
        )
        assert len(rows) == 1
        assert attempts["count"] == 2  # falhou uma vez, recuperou no retry
    finally:
        await client.aclose()
