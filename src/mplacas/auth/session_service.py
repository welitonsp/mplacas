from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.auth.db_models import AuthSessionRecord, LoginRateLimitRecord
from mplacas.core.jwt import JwtClaims, encode_refresh_token


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        ttl_seconds: int,
    ) -> str:
        expires_at = _utc_now() + timedelta(seconds=ttl_seconds)
        session_id = uuid.uuid4()
        token = encode_refresh_token(user_id, organization_id, jti=session_id)
        self._session.add(
            AuthSessionRecord(
                id=session_id,
                user_id=user_id,
                organization_id=organization_id,
                family_id=session_id,
                refresh_token_hash=hash_refresh_token(token),
                active=True,
                expires_at=expires_at,
            )
        )
        await self._session.flush()
        return token

    async def rotate(
        self,
        *,
        token: str,
        claims: JwtClaims,
        ttl_seconds: int,
    ) -> str | None:
        if claims.jti is None:
            return None
        now = _utc_now()
        token_hash = hash_refresh_token(token)
        new_session_id = uuid.uuid4()
        new_token = encode_refresh_token(claims.sub, claims.org_id, jti=new_session_id)
        claimed_family_id = (
            await self._session.execute(
                update(AuthSessionRecord)
                .where(
                    AuthSessionRecord.id == claims.jti,
                    AuthSessionRecord.active.is_(True),
                    AuthSessionRecord.user_id == claims.sub,
                    AuthSessionRecord.organization_id == claims.org_id,
                    AuthSessionRecord.refresh_token_hash == token_hash,
                    AuthSessionRecord.expires_at > now,
                )
                .values(active=False, rotated_at=now)
                .returning(AuthSessionRecord.family_id)
            )
        ).scalar_one_or_none()

        if claimed_family_id is None:
            await self._handle_failed_rotation(
                session_id=claims.jti,
                token_hash=token_hash,
                claims=claims,
                now=now,
            )
            return None

        self._session.add(
            AuthSessionRecord(
                id=new_session_id,
                user_id=claims.sub,
                organization_id=claims.org_id,
                family_id=claimed_family_id,
                refresh_token_hash=hash_refresh_token(new_token),
                active=True,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
        )
        await self._session.flush()
        await self._session.execute(
            update(AuthSessionRecord)
            .where(AuthSessionRecord.id == claims.jti)
            .values(replaced_by_session_id=new_session_id)
        )
        return new_token

    async def _handle_failed_rotation(
        self,
        *,
        session_id: uuid.UUID,
        token_hash: str,
        claims: JwtClaims,
        now: datetime,
    ) -> None:
        record = await self._session.get(AuthSessionRecord, session_id)
        if record is None:
            return
        token_matches = (
            record.user_id == claims.sub
            and record.organization_id == claims.org_id
            and record.refresh_token_hash == token_hash
        )
        if not token_matches:
            return
        if record.active and _as_utc(record.expires_at) <= now:
            record.active = False
            record.revoked_at = now
            await self._session.flush()
            return
        if record.active:
            return

        # O token autêntico já foi consumido/revogado: isso é replay. A
        # família inteira é invalidada para que o sucessor possivelmente
        # roubado não continue utilizável.
        await self._session.execute(
            update(AuthSessionRecord)
            .where(
                AuthSessionRecord.family_id == record.family_id,
                AuthSessionRecord.active.is_(True),
            )
            .values(active=False, revoked_at=now)
        )
        logger.warning(
            "refresh_token_replay_detected",
            extra={
                "auth_session_id": str(session_id),
                "auth_session_family_id": str(record.family_id),
                "user_id": str(record.user_id),
                "organization_id": str(record.organization_id),
            },
        )
        await self._session.flush()

    async def revoke(self, *, session_id: uuid.UUID) -> bool:
        record = await self._session.get(AuthSessionRecord, session_id)
        if record is None:
            return False
        if record.active:
            record.active = False
            record.revoked_at = _utc_now()
            await self._session.flush()
        return True

    async def revoke_all_for_organization(self, *, organization_id: uuid.UUID) -> int:
        """Revoke every currently-active session belonging to ``organization_id``.

        Used when an organization is deactivated: existing refresh tokens must
        stop working immediately, in addition to future login/refresh attempts
        already being blocked by the organization's ``active`` flag.
        """
        result = await self._session.execute(
            update(AuthSessionRecord)
            .where(
                AuthSessionRecord.organization_id == organization_id,
                AuthSessionRecord.active.is_(True),
            )
            .values(active=False, revoked_at=_utc_now())
        )
        await self._session.flush()
        return result.rowcount if isinstance(result, CursorResult) else 0


class LoginRateLimitService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def key_for(*, username: str, client_host: str | None) -> str:
        normalized_username = username.strip().lower() or "<blank>"
        normalized_host = (client_host or "unknown").strip().lower() or "unknown"
        digest = hashlib.sha256(
            f"{normalized_username}|{normalized_host}".encode("utf-8")
        ).hexdigest()
        return f"login:{digest}"

    async def is_locked(self, key: str) -> bool:
        record = await self._session.get(LoginRateLimitRecord, key)
        if record is None or record.locked_until is None:
            return False
        if _as_utc(record.locked_until) <= _utc_now():
            await self.clear(key)
            return False
        return True

    async def record_failure(
        self,
        key: str,
        *,
        max_attempts: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        now = _utc_now()
        record = await self._session.get(LoginRateLimitRecord, key)
        if record is None:
            record = LoginRateLimitRecord(
                key=key,
                attempt_count=0,
                first_attempt_at=now,
            )
            self._session.add(record)
        elif _as_utc(record.first_attempt_at) + timedelta(seconds=window_seconds) <= now:
            record.attempt_count = 0
            record.first_attempt_at = now
            record.locked_until = None

        record.attempt_count += 1
        if record.attempt_count >= max_attempts:
            record.locked_until = now + timedelta(seconds=lockout_seconds)
        await self._session.flush()

    async def clear(self, key: str) -> None:
        record = await self._session.get(LoginRateLimitRecord, key)
        if record is not None:
            await self._session.delete(record)
            await self._session.flush()
