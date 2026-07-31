"""``OperationsPrincipal`` / ``OperationsRole`` — the authenticated caller model.

Kept in its own module, independent of both ``core.security`` and
``core.tenancy``, so it can be imported by either without risk of a circular
import:

- ``core.security`` needs it to type its authentication dependencies
  (``require_operations_key`` / ``require_operations_read``) and re-exports it
  for backward compatibility with existing call sites.
- ``core.tenancy`` needs it as a real (non-``TYPE_CHECKING``) import to type
  ``resolve_read_plant`` / ``resolve_admin_plant`` — FastAPI resolves those
  annotations at runtime via ``typing.get_type_hints`` when building the
  dependency graph for ``ReadPlant`` / ``AdminPlant``, so the name must be a
  real symbol in ``core.tenancy``'s module namespace at import time, not a
  forward reference resolved later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status

from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE


class OperationsRole(StrEnum):
    ADMIN = "ADMIN"
    READ = "READ"


@dataclass(frozen=True, slots=True)
class OperationsPrincipal:
    role: OperationsRole
    credential_id: str
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE
    organization_id: uuid.UUID | None = None

    def can_read(self) -> bool:
        return self.role in {OperationsRole.ADMIN, OperationsRole.READ}

    def can_admin(self) -> bool:
        return self.role is OperationsRole.ADMIN

    def require_plant_access(self, plant_id: uuid.UUID) -> None:
        if not self.plant_scope.allows(plant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="plant not found",
            )

    def require_unrestricted_access(self) -> None:
        if self.plant_scope.is_restricted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="operational credential is restricted to plant resources",
            )
