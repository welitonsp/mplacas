"""ADR-093 — convite de clientes pelo dono da plataforma."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mplacas.audit.db_models import AuditEventRecord
from mplacas.clients.router import slugify
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord

_ENGINES: list = []
_CLIENTS: list = []
_KEY = {"X-API-Key": "synthetic-admin-key"}


def _make_client(monkeypatch, tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/clients.db"
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv("MPLACAS_DATABASE_URL", url)
    get_settings.cache_clear()

    import mplacas.auth.router as auth_router
    import mplacas.clients.router as clients_router
    import mplacas.db.session as db_session
    from mplacas.main import app

    engine = create_async_engine(url, poolclass=NullPool)
    _ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            if await session.get(OrganizationRecord, DEFAULT_ORGANIZATION_ID) is None:
                session.add(
                    OrganizationRecord(
                        id=DEFAULT_ORGANIZATION_ID, name="Dono", slug="default", active=True
                    )
                )
                await session.commit()

    asyncio.run(_prepare())
    monkeypatch.setattr(clients_router, "SessionFactory", factory)
    monkeypatch.setattr(auth_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    client = TestClient(app)
    _CLIENTS.append(client)
    return client, factory


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    while _CLIENTS:
        _CLIENTS.pop().close()
    while _ENGINES:
        asyncio.run(_ENGINES.pop().dispose())
    get_settings.cache_clear()


def _bearer(org_id: uuid.UUID, role: OperationsRole = OperationsRole.ADMIN) -> dict[str, str]:
    token = encode_access_token(uuid.uuid4(), org_id, role.value)
    return {"Authorization": f"Bearer {token}"}


def test_slugify_strips_accents_and_symbols() -> None:
    assert slugify("Usina do Rogério!") == "usina-do-rogerio"
    assert slugify("   ") == "cliente"


def test_operator_creates_client_with_invitation(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/platform/clients",
        json={"name": "Usina do Rogério", "admin_username": "rogerio@cliente.example"},
        headers=_KEY,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "usina-do-rogerio"
    token = body["invitation"]["token"]
    assert token and body["invitation"]["username"] == "rogerio@cliente.example"

    async def _audit():
        async with factory() as session:
            return list(await session.scalars(select(AuditEventRecord)))

    events = asyncio.run(_audit())
    assert [e.action for e in events] == ["platform.client_created"]
    # o token do convite nunca vai para a auditoria
    assert all(token not in repr(e.details) for e in events)

    listed = client.get("/platform/clients", headers=_KEY).json()["items"]
    assert len(listed) == 1
    assert listed[0]["name"] == "Usina do Rogério"
    assert listed[0]["admin_username"] == "rogerio@cliente.example"
    assert listed[0]["invitation_pending_until"] is not None
    assert listed[0]["plants"] == 0 and listed[0]["connections"] == 0
    assert "token" not in listed[0]


def test_same_name_gets_free_slug(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    first = client.post(
        "/platform/clients",
        json={"name": "Solar Sul", "admin_username": "a@sul.example"},
        headers=_KEY,
    )
    second = client.post(
        "/platform/clients",
        json={"name": "Solar Sul", "admin_username": "b@sul.example"},
        headers=_KEY,
    )
    assert first.json()["slug"] == "solar-sul"
    assert second.json()["slug"] == "solar-sul-2"


def test_invalid_admin_username_is_422(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.post(
        "/platform/clients",
        json={"name": "Solar Sul", "admin_username": "sem-email"},
        headers=_KEY,
    )
    assert response.status_code == 422
    assert client.get("/platform/clients", headers=_KEY).json()["items"] == []


def test_default_org_admin_is_platform_operator(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.get("/platform/clients", headers=_bearer(DEFAULT_ORGANIZATION_ID))
    assert response.status_code == 200


def test_client_admin_cannot_use_platform_routes(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    created = client.post(
        "/platform/clients",
        json={"name": "Cliente", "admin_username": "c@cli.example"},
        headers=_KEY,
    ).json()
    headers = _bearer(uuid.UUID(created["organization_id"]))

    assert client.get("/platform/clients", headers=headers).status_code == 403
    assert (
        client.post(
            "/platform/clients",
            json={"name": "Outro", "admin_username": "o@cli.example"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/platform/clients/{created['organization_id']}/invitation",
            json={},
            headers=headers,
        ).status_code
        == 403
    )


def test_default_org_read_user_is_forbidden(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    headers = _bearer(DEFAULT_ORGANIZATION_ID, OperationsRole.READ)
    assert client.get("/platform/clients", headers=headers).status_code == 403


def test_reinvite_revokes_pending_invitation(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    created = client.post(
        "/platform/clients",
        json={"name": "Cliente", "admin_username": "c@cli.example"},
        headers=_KEY,
    ).json()
    org_id = created["organization_id"]

    again = client.post(f"/platform/clients/{org_id}/invitation", json={}, headers=_KEY)

    assert again.status_code == 201
    assert again.json()["invitation"]["username"] == "c@cli.example"
    assert again.json()["invitation"]["token"] != created["invitation"]["token"]

    async def _invites():
        async with factory() as session:
            return list(
                await session.scalars(
                    select(UserInvitationRecord).order_by(UserInvitationRecord.created_at)
                )
            )

    invites = asyncio.run(_invites())
    assert len(invites) == 2
    assert invites[0].revoked_at is not None
    assert invites[1].revoked_at is None


def test_reinvite_unknown_or_default_org_is_404(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    assert (
        client.post(
            f"/platform/clients/{uuid.uuid4()}/invitation", json={}, headers=_KEY
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/platform/clients/{DEFAULT_ORGANIZATION_ID}/invitation", json={}, headers=_KEY
        ).status_code
        == 404
    )


def test_auth_me_reports_platform_operator(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    created = client.post(
        "/platform/clients",
        json={"name": "Cliente", "admin_username": "c@cli.example"},
        headers=_KEY,
    ).json()

    owner = client.get("/auth/me", headers=_bearer(DEFAULT_ORGANIZATION_ID))
    other = client.get("/auth/me", headers=_bearer(uuid.UUID(created["organization_id"])))

    assert owner.status_code == 200
    assert owner.json()["is_platform_operator"] is True
    assert other.status_code == 200
    assert other.json()["is_platform_operator"] is False
    assert other.json()["organization_name"] == "Cliente"


def test_invitation_responses_are_not_cached(monkeypatch, tmp_path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    created = client.post(
        "/platform/clients",
        json={"name": "Cliente", "admin_username": "c@cli.example"},
        headers=_KEY,
    )
    again = client.post(
        f"/platform/clients/{created.json()['organization_id']}/invitation",
        json={},
        headers=_KEY,
    )
    assert created.headers["cache-control"] == "no-store"
    assert again.headers["cache-control"] == "no-store"


def test_reinvite_keeps_other_role_invitations_and_uses_latest_admin(monkeypatch, tmp_path) -> None:
    from mplacas.organizations.invitation_service import InvitationService

    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = uuid.UUID(
        client.post(
            "/platform/clients",
            json={"name": "Cliente", "admin_username": "antigo@cli.example"},
            headers=_KEY,
        ).json()["organization_id"]
    )
    # dono trocou o e-mail do ADMIN num reenvio
    client.post(
        f"/platform/clients/{org_id}/invitation",
        json={"admin_username": "novo@cli.example"},
        headers=_KEY,
    )

    async def _invite_reader() -> None:
        async with factory() as session:
            await InvitationService(session).create(
                organization_id=org_id,
                username="leitor@cli.example",
                role=OperationsRole.READ,
                created_by_user_id=None,
                ttl_seconds=3600,
            )
            await session.commit()

    asyncio.run(_invite_reader())

    again = client.post(f"/platform/clients/{org_id}/invitation", json={}, headers=_KEY)

    assert again.json()["invitation"]["username"] == "novo@cli.example"

    async def _invites():
        async with factory() as session:
            return list(await session.scalars(select(UserInvitationRecord)))

    by_user = {}
    for record in asyncio.run(_invites()):
        by_user.setdefault(record.username, []).append(record)
    assert by_user["leitor@cli.example"][0].revoked_at is None
    assert [r.revoked_at is None for r in by_user["novo@cli.example"]].count(True) == 1


def test_concurrent_slug_conflict_is_409(monkeypatch, tmp_path) -> None:
    from sqlalchemy.exc import IntegrityError

    import mplacas.clients.router as clients_router

    client, _ = _make_client(monkeypatch, tmp_path)

    async def _lost_race(self, *args, **kwargs):
        raise IntegrityError("insert", {}, Exception("uq_organizations_slug"))

    monkeypatch.setattr(
        clients_router.OrganizationService, "create_with_bootstrap_admin", _lost_race
    )
    response = client.post(
        "/platform/clients",
        json={"name": "Cliente", "admin_username": "c@cli.example"},
        headers=_KEY,
    )
    assert response.status_code == 409
