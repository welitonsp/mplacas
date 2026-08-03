import logging
import uuid

import pytest
from fastapi import HTTPException
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import mplacas.core.security as security
from mplacas.core.authorization import PlantScope
from mplacas.core.config import Settings
from mplacas.core.principal import OperationsPrincipal
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
    )

    assert principal.role is OperationsRole.ADMIN
    assert principal.can_admin() is True
    assert principal.can_read() is True
    assert principal.credential_id.startswith("operations:admin:")
    assert "admin-key" not in principal.credential_id


def test_operations_auth_rejects_wrong_key_when_admin_key_configured() -> None:
    with pytest.raises(HTTPException) as exc_info:
        authenticate_operations_key("wrong-key", admin_key="admin-key")

    assert exc_info.value.status_code == 401


def test_operations_auth_logs_warning_when_static_admin_key_used(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="mplacas.core.security"):
        authenticate_operations_key(
            "admin-key",
            admin_key="admin-key",
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


def test_operations_auth_does_not_warn_when_key_is_wrong(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="mplacas.core.security"):
        with pytest.raises(HTTPException):
            authenticate_operations_key("wrong-key", admin_key="admin-key")

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


def test_operations_auth_rejects_admin_key_when_absent() -> None:
    """Regression guard for the historical 503 bug: a missing static key must
    surface as a plain 401 from ``authenticate_operations_key`` itself, not a
    503 -- the 401 is what lets ``_authenticate_with_fallback`` try the
    persisted-credential store next."""
    with pytest.raises(HTTPException) as exc_info:
        authenticate_operations_key(None, admin_key=None)

    assert exc_info.value.status_code == 401


# --- Etapa 1: fallback to persisted (tenant) credentials --------------------
#
# ``authenticate_operations_key`` only knows about the static admin key; the
# persisted-credential fallback lives in the async ``_authenticate_with_fallback``
# wrapper, so these tests exercise that layer directly, monkeypatching the
# database lookup rather than standing up a real session.


async def test_fallback_authenticates_persisted_credential_when_admin_key_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Etapa 1, teste 1: sem MPLACAS_OPERATIONS_API_KEY configurada, uma
    credencial de tenant persistida válida ainda autentica com sucesso e
    preserva seu próprio PlantScope (não vira admin/unrestricted)."""
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000040")
    expected_principal = OperationsPrincipal(
        role=OperationsRole.READ,
        credential_id="operations:read:persisted-fingerprint",
        plant_scope=PlantScope.restricted(frozenset({plant_id})),
        organization_id=uuid.uuid4(),
    )

    async def _fake_resolve(provided: str, *, require_admin: bool):
        assert provided == "tenant-secret"
        assert require_admin is False
        return expected_principal

    monkeypatch.setattr(security, "_resolve_persisted_credential", _fake_resolve)

    class _Settings:
        operations_api_key = None

    monkeypatch.setattr(security, "get_settings", lambda: _Settings())

    principal = await security._authenticate_with_fallback(
        "tenant-secret",
        require_admin=False,
    )

    assert principal is expected_principal
    assert principal.role is OperationsRole.READ
    assert principal.plant_scope.is_restricted is True
    assert principal.plant_scope.allows(plant_id) is True
    assert principal.organization_id == expected_principal.organization_id


async def test_fallback_returns_401_when_admin_key_absent_and_credential_unmatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Etapa 1, teste 2: sem chave estática configurada, uma credencial que
    não bate com nada (nem persistida) recebe 401, não 503."""

    async def _fake_resolve(provided: str, *, require_admin: bool):
        return None

    monkeypatch.setattr(security, "_resolve_persisted_credential", _fake_resolve)

    class _Settings:
        operations_api_key = None

    monkeypatch.setattr(security, "get_settings", lambda: _Settings())

    with pytest.raises(HTTPException) as exc_info:
        await security._authenticate_with_fallback(
            "unknown-secret",
            require_admin=False,
        )

    assert exc_info.value.status_code == 401


async def test_fallback_with_admin_key_configured_matches_current_production_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Etapa 1, teste 3: quando a chave estática está configurada (caso atual
    de produção), o resultado é idêntico ao anterior -- autentica como ADMIN
    sem sequer consultar o armazenamento persistido."""

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "persisted credential lookup must not run when the static key matches"
        )

    monkeypatch.setattr(security, "_resolve_persisted_credential", _fail_if_called)

    class _Secret:
        def get_secret_value(self) -> str:
            return "admin-key"

    class _Settings:
        operations_api_key = _Secret()

    monkeypatch.setattr(security, "get_settings", lambda: _Settings())

    principal = await security._authenticate_with_fallback(
        "admin-key",
        require_admin=True,
    )

    assert principal.role is OperationsRole.ADMIN
    assert principal.plant_scope.is_restricted is False


async def test_fallback_with_admin_key_configured_rejects_unknown_credential_with_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Etapa 1, teste 3 (continuação): com a chave estática configurada, uma
    credencial desconhecida ainda cai no fallback persistido e, não
    encontrando nada, resulta em 401 -- exatamente como hoje."""

    async def _fake_resolve(provided: str, *, require_admin: bool):
        return None

    monkeypatch.setattr(security, "_resolve_persisted_credential", _fake_resolve)

    class _Secret:
        def get_secret_value(self) -> str:
            return "admin-key"

    class _Settings:
        operations_api_key = _Secret()

    monkeypatch.setattr(security, "get_settings", lambda: _Settings())

    with pytest.raises(HTTPException) as exc_info:
        await security._authenticate_with_fallback(
            "wrong-key",
            require_admin=True,
        )

    assert exc_info.value.status_code == 401


async def test_fallback_with_no_credential_provided_returns_401_not_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Etapa 1, teste 4: caso de 503 avaliado e descartado. Depois do fix não
    existe mais um caso genuinamente "nenhum método disponível" alcançável a
    partir de ``_authenticate_with_fallback`` -- mesmo sem chave estática
    configurada e sem nenhuma credencial informada (``provided is None``), o
    resultado correto é 401 ("nenhuma credencial fornecida"), pois o
    armazenamento persistido continua sendo um método de autenticação
    disponível em princípio; ele simplesmente não pode ser consultado sem um
    valor de credencial para procurar. Isto prova que o 503 não é mais
    alcançável por essa rota; ``validate_operations_key`` (função separada,
    não tocada por esta mudança) continua sendo o único lugar do módulo que
    ainda produz 503 quando não configurada."""

    class _Settings:
        operations_api_key = None

    monkeypatch.setattr(security, "get_settings", lambda: _Settings())

    with pytest.raises(HTTPException) as exc_info:
        await security._authenticate_with_fallback(None, require_admin=False)

    assert exc_info.value.status_code == 401


def test_validate_operations_key_still_fails_closed_when_unconfigured() -> None:
    """The unrelated ``validate_operations_key`` helper (currently unused by
    any router, kept only for its own tests) is untouched by this change and
    keeps its original 503-when-unconfigured contract."""
    with pytest.raises(HTTPException) as exc_info:
        validate_operations_key("anything", None)

    assert exc_info.value.status_code == 503
