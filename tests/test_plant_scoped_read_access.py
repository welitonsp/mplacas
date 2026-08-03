from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialService
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

_SYNC_TEST_ENGINES: list = []
_SYNC_TEST_CLIENTS: list = []


@pytest.fixture(autouse=True)
def _dispose_sync_test_resources():
    yield
    while _SYNC_TEST_CLIENTS:
        _SYNC_TEST_CLIENTS.pop().close()
    while _SYNC_TEST_ENGINES:
        asyncio.run(_SYNC_TEST_ENGINES.pop().dispose())


def test_scoped_read_key_hides_out_of_scope_plant_resources(monkeypatch, tmp_path) -> None:
    """A plant-restricted persisted READ credential -- not a static key, which
    no longer supports plant scoping -- is denied 404 for out-of-scope plants,
    the same observable behavior the old static ``MPLACAS_OPERATIONS_READ_API_KEY``
    plus ``MPLACAS_OPERATIONS_READ_PLANT_IDS`` combination used to provide."""
    allowed_plant_id = uuid.UUID("00000000-0000-0000-0000-000000000040")
    denied_plant_id = uuid.UUID("00000000-0000-0000-0000-000000000041")
    bill_id = uuid.UUID("00000000-0000-0000-0000-000000000042")

    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/plant-scoped-read.db",
    )
    get_settings.cache_clear()

    import mplacas.db.session as db_session

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/plant-scoped-read.db",
        poolclass=NullPool,
    )
    _SYNC_TEST_ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> str:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            org = OrganizationRecord(name="Org Restrita", slug="org-restrita", active=True)
            session.add(org)
            await session.flush()
            session.add(
                Plant(id=allowed_plant_id, organization_id=org.id, name="Usina Permitida")
            )
            await session.flush()
            _, secret = await CredentialService(session).create(
                name="cred-read-restrita",
                role=OperationsRole.READ,
                organization_id=org.id,
                plant_ids=frozenset({allowed_plant_id}),
            )
            await session.commit()
            return secret

    secret = asyncio.run(_prepare())
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    client = TestClient(app)
    _SYNC_TEST_CLIENTS.append(client)
    headers = {"X-API-Key": secret}

    requests = (
        (f"/energy/cycles/{bill_id}", {"plant_id": str(denied_plant_id)}),
        ("/energy/trends/latest", {"plant_id": str(denied_plant_id)}),
        ("/energy/executive/latest", {"plant_id": str(denied_plant_id)}),
        (
            "/energy/anomalies/latest",
            {
                "plant_id": str(denied_plant_id),
                "expected_daily_production_kwh": "10",
            },
        ),
        ("/energy/explanations/latest", {"plant_id": str(denied_plant_id)}),
        ("/reports/monthly/latest", {"plant_id": str(denied_plant_id)}),
    )

    for path, params in requests:
        response = client.get(path, headers=headers, params=params)
        assert response.status_code == 404
        assert response.json() == {"detail": "plant not found"}

    get_settings.cache_clear()
