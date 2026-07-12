import pytest
from fastapi import HTTPException

from mplacas.core.security import validate_operations_key


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
