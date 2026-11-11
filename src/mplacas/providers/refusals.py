"""Tradução de erro do provedor em recusa auditada e resposta HTTP.

Função pura (sem banco nem rede): dado o erro, diz o motivo (que vai para a
auditoria e para o ``detail`` da resposta) e o status HTTP. Quem chama continua
dono da ordem ``await refuse(...)`` antes de ``raise``.
"""

from dataclasses import dataclass

from fastapi import status

from mplacas.providers.accounts import GROWATT_TOKEN
from mplacas.providers.base import (
    ProviderAuthError,
    ProviderBlockedError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)


@dataclass(frozen=True, slots=True)
class ProviderRefusal:
    reason: str  # vai para a auditoria e para o detail da resposta
    status_code: int


def refusal_for(
    provider: str, exc: ProviderError, *, only_auth_is_credentials: bool
) -> ProviderRefusal:
    """Motivo e status HTTP para um erro do provedor.

    ``ProviderBlockedError`` herda de ``ProviderAuthError``: por isso limite de
    taxa e bloqueio são tratados antes de olhar a autenticação.

    ``only_auth_is_credentials`` é a única diferença real entre os dois usos:

    - ``True`` (importação de histórico): só ``ProviderAuthError`` vira 422;
      qualquer outro erro do provedor, em qualquer marca, é 503 indisponível.
    - ``False`` (verificação da conta): indisponibilidade é 503; na Growatt por
      token, erro que não é de autenticação também (não é o token); o resto
      (auth e formato inesperado) vira 422 de login/token recusado.
    """
    if isinstance(exc, ProviderRateLimitedError):
        return ProviderRefusal("provider_rate_limited", status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, ProviderBlockedError):
        return ProviderRefusal("provider_login_blocked", status.HTTP_503_SERVICE_UNAVAILABLE)
    unavailable = ProviderRefusal("provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
    if only_auth_is_credentials:
        if not isinstance(exc, ProviderAuthError):
            return unavailable
    elif isinstance(exc, ProviderUnavailableError) or (
        provider == GROWATT_TOKEN and not isinstance(exc, ProviderAuthError)
    ):
        return unavailable
    reason = "provider_token_failed" if provider == GROWATT_TOKEN else "provider_login_failed"
    return ProviderRefusal(reason, status.HTTP_422_UNPROCESSABLE_CONTENT)
