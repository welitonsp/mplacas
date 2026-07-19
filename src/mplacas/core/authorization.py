from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class PlantScope:
    """Immutable set of plants visible to an operational principal."""

    plant_ids: frozenset[uuid.UUID] | None = None

    @classmethod
    def unrestricted(cls) -> Self:
        return cls()

    @classmethod
    def restricted(cls, plant_ids: Iterable[uuid.UUID]) -> Self:
        normalized = frozenset(plant_ids)
        if not normalized:
            raise ValueError("a restricted plant scope must contain at least one plant")
        return cls(plant_ids=normalized)

    @property
    def is_restricted(self) -> bool:
        return self.plant_ids is not None

    def allows(self, plant_id: uuid.UUID) -> bool:
        return self.plant_ids is None or plant_id in self.plant_ids


UNRESTRICTED_PLANT_SCOPE = PlantScope.unrestricted()
