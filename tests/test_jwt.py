from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from pydantic import ValidationError

from mplacas.core.config import Settings, get_settings
from mplacas.core.jwt import JwtError, decode_token, encode_access_token

_SECRET = "test-jwt-secret-at-least-64-bytes-long-for-all-hmac-test-algorithms"
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000102")


@pytest.fixture(autouse=True)
def _jwt_settings(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", _SECRET)
    monkeypatch.setenv("MPLACAS_JWT_KEY_ID", "current-v2")
    monkeypatch.setenv("MPLACAS_JWT_AUDIENCE", "mplacas-api")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _raw_access_token(
    *,
    audience: str = "mplacas-api",
    role: str = "READ",
    algorithm: str = "HS256",
    key_id: str = "current-v2",
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(_USER_ID),
            "org_id": str(_ORG_ID),
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": "mplacas",
            "aud": audience,
            "type": "access",
        },
        _SECRET,
        algorithm=algorithm,
        headers={"kid": key_id},
    )


def test_access_token_requires_expected_audience_and_key_id() -> None:
    claims = decode_token(
        encode_access_token(_USER_ID, _ORG_ID, "ADMIN"),
        expected_type="access",
    )
    assert claims.role == "ADMIN"

    with pytest.raises(JwtError):
        decode_token(_raw_access_token(audience="other-api"), expected_type="access")
    with pytest.raises(JwtError, match="unknown token key id"):
        decode_token(_raw_access_token(key_id="unknown"), expected_type="access")


def test_access_token_rejects_non_allowlisted_algorithm_and_role() -> None:
    with pytest.raises(JwtError, match="algorithm"):
        decode_token(_raw_access_token(algorithm="HS384"), expected_type="access")
    with pytest.raises(JwtError, match="role"):
        decode_token(_raw_access_token(role="PLATFORM_OWNER"), expected_type="access")


def test_previous_key_is_accepted_during_rotation(monkeypatch) -> None:
    previous_secret = "previous-jwt-secret-at-least-32-bytes"
    monkeypatch.setenv("MPLACAS_JWT_PREVIOUS_SECRET", previous_secret)
    monkeypatch.setenv("MPLACAS_JWT_PREVIOUS_KEY_ID", "previous-v1")
    get_settings.cache_clear()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(_USER_ID),
            "org_id": str(_ORG_ID),
            "role": "READ",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": "mplacas",
            "aud": "mplacas-api",
            "type": "access",
        },
        previous_secret,
        algorithm="HS256",
        headers={"kid": "previous-v1"},
    )

    assert decode_token(token, expected_type="access").sub == _USER_ID


def test_configuration_rejects_short_secret_and_non_allowlisted_algorithm() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(_env_file=None, jwt_secret="short-secret")
    with pytest.raises(ValidationError, match="HS256"):
        Settings(
            _env_file=None,
            jwt_secret=_SECRET,
            jwt_algorithm="HS512",  # type: ignore[arg-type]
        )
