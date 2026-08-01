from datetime import date
from decimal import Decimal

import httpx
import pytest

from mplacas.providers.base import ProviderSchemaError
from mplacas.providers.nepviewer.client import NepViewerClient


@pytest.mark.asyncio
async def test_auth_and_list_devices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sign-in"):
            return httpx.Response(200, json={"data": {"tokenInfo": {"token": "safe-token"}}})
        assert request.headers["Authorization"] == "safe-token"
        return httpx.Response(
            200,
            json={
                "data": {
                    "list": [
                        {
                            "sn": "ABC123",
                            "modelName": "BDM",
                            "city": "Caldas Novas",
                            "lastUpdate": "12/07/2026 12:30:00",
                        }
                    ]
                }
            },
        )

    async with NepViewerClient(
        account="user@example.com",
        password="secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        devices = await client.list_devices()

    assert devices[0].serial_number == "ABC123"
    assert devices[0].city == "Caldas Novas"


@pytest.mark.asyncio
async def test_schema_drift_is_explicit() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    async with NepViewerClient(
        account="user@example.com",
        password="secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ProviderSchemaError):
            await client.list_devices()


@pytest.mark.asyncio
async def test_get_daily_energy_parses_date_only_xaxis_from_real_api_shape() -> None:
    """Regressão: a API real do device/statistics/echarts devolve xAxisData
    no formato DD/MM/AAAA, sem componente de hora (reproduzido contra a API
    real em 2026-07-31). Um mock com hora nunca teria pego essa quebra."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sign-in"):
            return httpx.Response(200, json={"data": {"tokenInfo": {"token": "safe-token"}}})
        return httpx.Response(
            200,
            json={
                "data": {
                    "legend": ["Power Generation"],
                    "xAxisData": ["29/07/2026", "30/07/2026", "31/07/2026"],
                    "series": [
                        {
                            "stack": "",
                            "name": "Power Generation",
                            "unit": "",
                            "data": [6.9, 8.8, 9.189],
                        }
                    ],
                    "weatherSeries": None,
                }
            },
        )

    async with NepViewerClient(
        account="user@example.com",
        password="secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        rows = await client.get_daily_energy(
            "ABC123", date(2026, 7, 29), date(2026, 7, 31)
        )

    assert [row.production_date for row in rows] == [
        date(2026, 7, 29),
        date(2026, 7, 30),
        date(2026, 7, 31),
    ]
    assert [row.energy_kwh for row in rows] == [
        Decimal("6.9"),
        Decimal("8.8"),
        Decimal("9.189"),
    ]
