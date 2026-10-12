"""Request models for the ``/organizations`` API.

Moved verbatim from ``organizations.router`` so ``organizations.service`` can
accept them without importing the HTTP layer.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from mplacas.core.principal import OperationsRole

_SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80, pattern=_SLUG_PATTERN)
    admin_username: str = Field(min_length=1, max_length=80)


class InvitationCreateRequest(BaseModel):
    # Deliberately no ``organization_id`` field: it is always derived from
    # ``principal.organization_id`` (see ``create_invitation``), never
    # accepted from the request body, following the same convention as
    # ``credentials.router._resolve_organization_id``.
    username: str = Field(min_length=1, max_length=80)
    role: OperationsRole


class OrganizationUpdateRequest(BaseModel):
    """Partial update for an organization's Telegram linkage and default plant.

    Only ``telegram_chat_id``, ``telegram_allowed_user_id`` and
    ``default_plant_id`` are editable here (name/slug/active are out of scope
    for this endpoint). A field omitted from the request body is left
    untouched; a field sent explicitly as ``null`` clears (unlinks) the
    corresponding column. All fields default to ``None``, and
    ``model_fields_set`` (Pydantic's own tracking of which fields were present
    in the parsed payload) is what distinguishes "omitted" from "sent as
    null" in ``OrganizationService.update`` — not the field's value itself.
    """

    telegram_chat_id: int | None = None
    telegram_allowed_user_id: int | None = None
    default_plant_id: uuid.UUID | None = None
