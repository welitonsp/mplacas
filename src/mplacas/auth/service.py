"""Credential checks behind ``/auth``, independent of the HTTP layer.

Moved verbatim from ``auth.router``. Transaction control (including the
commit of a failed attempt *before* answering 401/400, so rate limiting
survives the error) deliberately stays in the router: those commits are part
of the endpoint's security contract, not reusable domain logic.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.auth.password import hash_password, verify_password
from mplacas.auth.session_service import LoginRateLimitService
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.organizations.db_models import OrganizationRecord

# Verified against when the user does not exist (or has no password), so a
# login for an unknown username costs the same Argon2 work as a real one and
# response timing does not reveal which usernames exist.
DUMMY_PASSWORD_HASH = hash_password("mplacas-invalid-user-dummy-password")


async def load_active_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    username: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> OperationalUserRecord | None:
    """Return the matching user only if both it and its organization are active.

    A user without organization (platform user) only needs to be active
    itself; the outer join keeps it in the result.
    """
    statement = select(OperationalUserRecord).outerjoin(
        OrganizationRecord,
        OperationalUserRecord.organization_id == OrganizationRecord.id,
    )
    if user_id is not None:
        statement = statement.where(OperationalUserRecord.id == user_id)
    if username is not None:
        statement = statement.where(OperationalUserRecord.name == username)
    if organization_id is not None:
        statement = statement.where(
            OperationalUserRecord.organization_id == organization_id
        )
    statement = statement.where(
        OperationalUserRecord.active.is_(True),
        or_(OrganizationRecord.id.is_(None), OrganizationRecord.active.is_(True)),
    )
    return await session.scalar(statement)


def verify_candidate_password(
    *,
    supplied_password: str,
    user: OperationalUserRecord | None,
) -> bool:
    if user is None or user.password_hash is None:
        verify_password(supplied_password, DUMMY_PASSWORD_HASH)
        return False
    return verify_password(supplied_password, user.password_hash)


def invitation_rate_key(*, token: str, client_host: str | None) -> str:
    # The token itself must never be logged or used verbatim as a rate-limit
    # key (it would defeat hashing at rest in ``LoginRateLimitRecord``); a
    # truncated SHA-256 digest plays the same role ``username`` plays for
    # ``/auth/login``, reusing ``LoginRateLimitService.key_for`` as-is rather
    # than inventing a parallel rate-limit mechanism.
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return LoginRateLimitService.key_for(username=token_digest, client_host=client_host)
