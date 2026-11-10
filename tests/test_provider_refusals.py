import pytest
from fastapi import status

from mplacas.providers.accounts import GROWATT, GROWATT_TOKEN, NEPVIEWER
from mplacas.providers.base import (
    ProviderAuthError,
    ProviderBlockedError,
    ProviderError,
    ProviderIncompleteDataError,
    ProviderRateLimitedError,
    ProviderSchemaError,
    ProviderUnavailableError,
)
from mplacas.providers.refusals import ProviderRefusal, refusal_for

S503 = status.HTTP_503_SERVICE_UNAVAILABLE
S422 = status.HTTP_422_UNPROCESSABLE_CONTENT

# Verificação da conta (only_auth_is_credentials=False)
_VERIFY = {
    ProviderRateLimitedError: ("provider_rate_limited", S503),
    ProviderBlockedError: ("provider_login_blocked", S503),
    ProviderUnavailableError: ("provider_unavailable", S503),
}
# Importação de histórico (only_auth_is_credentials=True)
_HISTORY = {
    ProviderRateLimitedError: ("provider_rate_limited", S503),
    ProviderBlockedError: ("provider_login_blocked", S503),
    ProviderUnavailableError: ("provider_unavailable", S503),
    ProviderSchemaError: ("provider_unavailable", S503),
    ProviderIncompleteDataError: ("provider_unavailable", S503),
    ProviderError: ("provider_unavailable", S503),
}


def _creds(provider: str) -> tuple[str, int]:
    reason = "provider_token_failed" if provider == GROWATT_TOKEN else "provider_login_failed"
    return reason, S422


def _verify_expected(provider: str, exc_cls: type[ProviderError]) -> tuple[str, int]:
    if exc_cls in _VERIFY:
        return _VERIFY[exc_cls]
    if provider == GROWATT_TOKEN and not issubclass(exc_cls, ProviderAuthError):
        return "provider_unavailable", S503
    return _creds(provider)


_PROVIDERS = [NEPVIEWER, GROWATT, GROWATT_TOKEN]
_EXCEPTIONS = [
    ProviderRateLimitedError,
    ProviderBlockedError,
    ProviderUnavailableError,
    ProviderAuthError,
    ProviderSchemaError,
    ProviderIncompleteDataError,
    ProviderError,
]


@pytest.mark.parametrize("provider", _PROVIDERS)
@pytest.mark.parametrize("exc_cls", _EXCEPTIONS)
def test_verificacao_da_conta(provider: str, exc_cls: type[ProviderError]) -> None:
    reason, code = _verify_expected(provider, exc_cls)
    assert refusal_for(provider, exc_cls("x"), only_auth_is_credentials=False) == ProviderRefusal(
        reason, code
    )


@pytest.mark.parametrize("provider", _PROVIDERS)
@pytest.mark.parametrize("exc_cls", _EXCEPTIONS)
def test_importacao_de_historico(provider: str, exc_cls: type[ProviderError]) -> None:
    reason, code = _HISTORY[exc_cls] if exc_cls in _HISTORY else _creds(provider)
    assert refusal_for(provider, exc_cls("x"), only_auth_is_credentials=True) == ProviderRefusal(
        reason, code
    )


def test_tabela_explicita_de_casos_que_divergem() -> None:
    # Erro de formato: 422 na conta (NEPViewer/Growatt), 503 no histórico.
    assert refusal_for(NEPVIEWER, ProviderSchemaError("x"), only_auth_is_credentials=False) == (
        ProviderRefusal("provider_login_failed", S422)
    )
    assert refusal_for(NEPVIEWER, ProviderSchemaError("x"), only_auth_is_credentials=True) == (
        ProviderRefusal("provider_unavailable", S503)
    )
    # Growatt por token: formato inesperado nunca culpa o token.
    assert refusal_for(GROWATT_TOKEN, ProviderSchemaError("x"), only_auth_is_credentials=False) == (
        ProviderRefusal("provider_unavailable", S503)
    )
