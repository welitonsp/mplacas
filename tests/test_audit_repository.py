from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.audit.db_models import AuditEventRecord
from mplacas.audit.repository import AuditEventRepository
from mplacas.core.security import OperationsPrincipal, OperationsRole
from mplacas.db.base import Base


@pytest.mark.asyncio
async def test_audit_event_records_actor_fingerprint_without_secret() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    request = SimpleNamespace(
        state=SimpleNamespace(
            request_id="audit-request-1",
            operations_principal=OperationsPrincipal(
                role=OperationsRole.ADMIN,
                credential_id="operations:admin:abc123",
            ),
        )
    )
    async with factory() as session:
        await AuditEventRepository(session).record(  # type: ignore[arg-type]
            request,
            action="billing.confirm",
            resource_type="utility_bill",
            resource_id="bill-1",
            outcome="SUCCEEDED",
            details={"plant_id": "plant-1"},
        )
        await session.commit()

        event = (await session.execute(select(AuditEventRecord))).scalar_one()
        assert event.action == "billing.confirm"
        assert event.actor_role == "ADMIN"
        assert event.actor_credential_id == "operations:admin:abc123"
        assert event.request_id == "audit-request-1"
        assert event.details == {"plant_id": "plant-1"}
        assert "secret" not in str(event.details).casefold()

    await engine.dispose()
