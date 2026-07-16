import pytest
from fastapi import HTTPException

from mplacas.core.security import (
    OperationsRole,
    authenticate_operations_key,
    validate_operations_key,
)


def test_operations_key_accepts_exact_match() -> None:
    validate_operations_key("secret-value", "secret-value")


def test_operations_key_rejects_invalid_value() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_operations_key("wrong", "secret-value")
    assert exc_info.value.status_code == 401


def test_operations_key_fails_closed_without_configuration() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_operations_key("anything", None)
    assert exc_info.value.status_code == 503


def test_operations_auth_returns_admin_principal_for_admin_key() -> None:
    principal = authenticate_operations_key(
        "admin-key",
        admin_key="admin-key",
        read_key="read-key",
    )

    assert principal.role is OperationsRole.ADMIN
    assert principal.can_admin() is True
    assert principal.can_read() is True
    assert principal.credential_id.startswith("operations:admin:")
    assert "admin-key" not in principal.credential_id


def test_operations_auth_returns_read_principal_for_read_key() -> None:
    principal = authenticate_operations_key(
        "read-key",
        admin_key="admin-key",
        read_key="read-key",
    )

    assert principal.role is OperationsRole.READ
    assert principal.can_admin() is False
    assert principal.can_read() is True
    assert principal.credential_id.startswith("operations:read:")
    assert "read-key" not in principal.credential_id


def test_operations_admin_auth_rejects_read_key() -> None:
    with pytest.raises(HTTPException) as exc_info:
        authenticate_operations_key(
            "read-key",
            admin_key="admin-key",
            read_key="read-key",
            require_admin=True,
        )

    assert exc_info.value.status_code == 401
