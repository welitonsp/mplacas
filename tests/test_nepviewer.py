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
