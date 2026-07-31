import logging
import uuid

import pytest
from fastapi import HTTPException
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from mplacas.core.config import Settings
from mplacas.core.security import (
    OperationsRole,
    authenticate_operations_key,
    validate_operations_key,
)
from mplacas.observability.metrics import (
    OUTCOME_SUCCESS,
    configure_metrics,
    reset_metrics_state_for_tests,
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
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000040")
    principal = authenticate_operations_key(
        "read-key",
        admin_key="admin-key",
        read_key="read-key",
        read_plant_ids=frozenset({plant_id}),
    )

    assert principal.role is OperationsRole.READ
    assert principal.can_admin() is False
    assert principal.can_read() is True
    assert principal.credential_id.startswith("operations:read:")
    assert "read-key" not in principal.credential_id
    assert principal.plant_scope.is_restricted is True
    assert principal.plant_scope.allows(plant_id) is True


def test_restricted_principal_hides_out_of_scope_plant_and_denies_global_access() -> None:
    allowed_plant_id = uuid.UUID("00000000-0000-0000-0000-000000000040")
    denied_plant_id = uuid.UUID("00000000-0000-0000-0000-000000000041")
    principal = authenticate_operations_key(
        "read-key",
        admin_key="admin-key",
        read_key="read-key",
        read_plant_ids=frozenset({allowed_plant_id}),
    )

    principal.require_plant_access(allowed_plant_id)
    with pytest.raises(HTTPException) as plant_error:
        principal.require_plant_access(denied_plant_id)
    with pytest.raises(HTTPException) as global_error:
        principal.require_unrestricted_access()

    assert plant_error.value.status_code == 404
    assert global_error.value.status_code == 403


def test_admin_principal_remains_unrestricted_when_read_scope_is_configured() -> None:
    principal = authenticate_operations_key(
        "admin-key",
        admin_key="admin-key",
        read_key="read-key",
        read_plant_ids=frozenset(
            {uuid.UUID("00000000-0000-0000-0000-000000000040")}
        ),
    )

    assert principal.role is OperationsRole.ADMIN
    assert principal.plant_scope.is_restricted is False
    principal.require_plant_access(
        uuid.UUID("00000000-0000-0000-0000-000000000041")
    )
    principal.require_unrestricted_access()


def test_operations_auth_logs_warning_when_static_admin_key_used(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="mplacas.core.security"):
        authenticate_operations_key(
            "admin-key",
            admin_key="admin-key",
            read_key="read-key",
            http_method="GET",
            http_path="/operations/plants",
        )

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.message == "operations_static_key_auth_used"
    assert record.operations_role == "ADMIN"
    assert record.http_method == "GET"
    assert record.http_path == "/operations/plants"
    assert "admin-key" not in record.credential_id


def test_operations_auth_logs_warning_when_static_read_key_used(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="mplacas.core.security"):
        authenticate_operations_key(
            "read-key",
            admin_key="admin-key",
            read_key="read-key",
        )

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].operations_role == "READ"
    assert "read-key" not in warnings[0].credential_id


def test_operations_auth_does_not_warn_when_bearer_would_be_used_instead(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="mplacas.core.security"):
        with pytest.raises(HTTPException):
            authenticate_operations_key(
                "wrong-key",
                admin_key="admin-key",
                read_key="read-key",
            )

    assert not any(
        record.message == "operations_static_key_auth_used"
        for record in caplog.records
    )


def test_operations_auth_records_static_key_metric() -> None:
    reader = InMemoryMetricReader()
    settings = Settings(_env_file=None)
    configure_metrics(settings=settings, service_name="mplacas-test", reader=reader)
    try:
        authenticate_operations_key(
            "admin-key",
            admin_key="admin-key",
            read_key="read-key",
        )

        data = reader.get_metrics_data()
        assert data is not None
        counter_points = [
            point
            for resource_metric in data.resource_metrics
            for scope_metric in resource_metric.scope_metrics
            for metric in scope_metric.metrics
            if metric.name == "mplacas.operation.runs"
            for point in metric.data.data_points
        ]
        assert any(
            dict(point.attributes)
            == {"operation": "static_key_auth_admin", "outcome": OUTCOME_SUCCESS}
            for point in counter_points
        )
    finally:
        reset_metrics_state_for_tests()


def test_operations_admin_auth_rejects_read_key() -> None:
    with pytest.raises(HTTPException) as exc_info:
        authenticate_operations_key(
            "read-key",
            admin_key="admin-key",
            read_key="read-key",
            require_admin=True,
        )

    assert exc_info.value.status_code == 401
