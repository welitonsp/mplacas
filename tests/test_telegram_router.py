from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from mplacas.telegram.router import (
    _resolve_telegram_organization,
    _resolve_telegram_plant_scope,
)


class FakeScalarResult:
    def __init__(self, values: list) -> None:
        self._values = values

    def scalars(self):
        return self._values

    def scalar_one_or_none(self):
        if not self._values:
            return None
        return self._values[0]


class FakeSession:
    """Fake session returning canned rows regardless of the statement shape.

    Good enough for these unit tests, which only exercise
    ``_resolve_telegram_organization``/``_resolve_telegram_plant_scope`` in
    isolation with pre-seeded return values (the organization-scoped plant
    inference itself is covered end-to-end by
    ``core.tenancy``/``test_tenancy.py`` and by the cross-tenant webhook test
    below).
    """

    def __init__(self, values: list) -> None:
        self._values = values

    async def execute(self, statement):
        return FakeScalarResult(self._values)


@pytest.mark.asyncio
async def test_resolve_telegram_organization_returns_matching_organization() -> None:
    organization_id = uuid.uuid4()

    resolved = await _resolve_telegram_organization(
        FakeSession([organization_id]),  # type: ignore[arg-type]
        chat_id=123,
    )

    assert resolved == organization_id


@pytest.mark.asyncio
async def test_resolve_telegram_organization_rejects_unknown_chat() -> None:
    with pytest.raises(HTTPException) as exc:
        await _resolve_telegram_organization(
            FakeSession([]),  # type: ignore[arg-type]
            chat_id=999,
        )

    assert exc.value.status_code == 403
    assert "not linked to any organization" in exc.value.detail


@pytest.mark.asyncio
async def test_resolve_telegram_plant_scope_reuses_the_given_session() -> None:
    """``_resolve_telegram_plant_scope`` delegates to
    ``core.tenancy._infer_single_plant_for_organization_in_session``, which
    queries against the ``session`` passed in — no second session/connection
    is opened. See ``test_telegram_webhook_cross_tenant.py`` for full
    integration coverage (0/1/>1 plant scenarios, cross-tenant isolation)."""
    plant_id = uuid.uuid4()
    organization_id = uuid.uuid4()

    resolved = await _resolve_telegram_plant_scope(
        FakeSession([plant_id]),  # type: ignore[arg-type]
        organization_id,
    )

    assert resolved == plant_id


@pytest.mark.asyncio
async def test_resolve_telegram_plant_scope_rejects_ambiguous_scope() -> None:
    organization_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        await _resolve_telegram_plant_scope(
            FakeSession([uuid.uuid4(), uuid.uuid4()]),  # type: ignore[arg-type]
            organization_id,
        )

    assert exc.value.status_code == 409
