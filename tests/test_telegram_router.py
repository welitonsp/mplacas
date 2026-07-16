from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from mplacas.telegram.router import _resolve_telegram_plant_scope


class FakeScalarResult:
    def __init__(self, values: list[uuid.UUID]) -> None:
        self._values = values

    def scalars(self) -> list[uuid.UUID]:
        return self._values


class FakeSession:
    def __init__(self, plant_ids: list[uuid.UUID]) -> None:
        self._plant_ids = plant_ids

    async def execute(self, statement):
        return FakeScalarResult(self._plant_ids)


@pytest.mark.asyncio
async def test_telegram_bill_intake_resolves_single_plant_scope() -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000041")

    resolved = await _resolve_telegram_plant_scope(FakeSession([plant_id]))  # type: ignore[arg-type]

    assert resolved == plant_id


@pytest.mark.asyncio
async def test_telegram_bill_intake_rejects_ambiguous_plant_scope() -> None:
    first = uuid.UUID("00000000-0000-0000-0000-000000000041")
    second = uuid.UUID("00000000-0000-0000-0000-000000000042")

    with pytest.raises(HTTPException) as exc:
        await _resolve_telegram_plant_scope(FakeSession([first, second]))  # type: ignore[arg-type]

    assert exc.value.status_code == 409
    assert "exactly one configured plant" in exc.value.detail
