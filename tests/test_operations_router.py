import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialService
from mplacas.db.base import Base
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


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeJobRunRepository:
    def __init__(self, session) -> None:
        self.session = session

    async def list_recent(self, limit: int = 20) -> list[object]:
        return []


def test_operations_endpoints_require_operational_key(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    get_settings.cache_clear()
    client = TestClient(app)

    for path in ("/operations/jobs", "/operations/status"):
        response = client.get(path)
        assert response.status_code == 401

    get_settings.cache_clear()


def test_operations_admin_key_can_access_read_endpoint(monkeypatch, caplog) -> None:
    """The static ``MPLACAS_OPERATIONS_API_KEY`` (ADMIN role) is unrestricted
    by default and can reach org-wide read endpoints such as
    ``/operations/jobs``. Read-only access to endpoints like this now comes
    exclusively from a persisted ADMIN-equivalent, unrestricted credential --
    there is no more static READ key that grants org-wide access."""
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    get_settings.cache_clear()
    import mplacas.operations.router as operations_router

    monkeypatch.setattr(operations_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(operations_router, "JobRunRepository", FakeJobRunRepository)
    caplog.set_level("INFO", logger="mplacas.main")

    response = TestClient(app).get(
        "/operations/jobs",
        headers={"X-API-Key": "synthetic-admin-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"count": 0, "items": []}
    matching = [
        record
        for record in caplog.records
        if record.name == "mplacas.main" and record.message == "http_request_completed"
    ]
    assert matching
    assert matching[-1].operations_role == "ADMIN"
    assert matching[-1].operations_credential_id.startswith("operations:admin:")
    assert "synthetic-admin-key" not in matching[-1].operations_credential_id
    get_settings.cache_clear()


def test_scoped_read_credential_cannot_access_global_operational_endpoints(
    monkeypatch, tmp_path
) -> None:
    """A persisted READ credential -- the only way to grant read access today,
    since the static READ key was removed -- always carries an
    organization-derived (therefore restricted) ``PlantScope`` and is denied
    403 on org-wide, unrestricted-only endpoints like ``/operations/jobs``."""
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/scoped-read-credential.db",
    )
    get_settings.cache_clear()

    import mplacas.db.session as db_session

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/scoped-read-credential.db",
        poolclass=NullPool,
    )
    _SYNC_TEST_ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> str:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            org = OrganizationRecord(name="Org Leitura", slug="org-leitura", active=True)
            session.add(org)
            await session.flush()
            _, secret = await CredentialService(session).create(
                name="cred-read-global",
                role=OperationsRole.READ,
                organization_id=org.id,
            )
            await session.commit()
            return secret

    secret = asyncio.run(_prepare())
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    client = TestClient(app)
    _SYNC_TEST_CLIENTS.append(client)

    for path in ("/operations/jobs", "/operations/status"):
        response = client.get(path, headers={"X-API-Key": secret})
        assert response.status_code == 403

    get_settings.cache_clear()
