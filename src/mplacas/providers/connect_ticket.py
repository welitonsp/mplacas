"""Bilhete da primeira conexão (ADR-096): liga a prévia à confirmação.

Na prévia, o servidor confere a conta na marca e lê a usina, mas não salva
nada. Para o "Salvar usina" não precisar consultar a marca de novo (a Growatt
bloqueia excesso de logins) nem o navegador guardar a senha, o servidor
devolve um bilhete cifrado com AES-256-GCM (``core.secret_box``): marca,
credencial, aparelhos encontrados e a usina montada. Só o servidor abre; o
bilhete é amarrado à organização (AAD) e vence em 15 minutos.

Nada aqui registra o conteúdo do bilhete em log, exceção ou ``repr``.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from mplacas.core.secret_box import SealedSecret, SecretBox, SecretBoxError
from mplacas.providers.accounts import ProviderLogin

TICKET_TTL = timedelta(minutes=15)
MAX_TICKET_CHARS = 16384


class ConnectTicketError(ValueError):
    """Bilhete inválido, vencido ou de outra organização (mensagem genérica)."""


@dataclass(frozen=True, slots=True)
class ConnectTicket:
    provider: str
    credentials: ProviderLogin = field(repr=False)
    serials: list[str]
    # Usina montada na prévia: valores (texto) e origem de cada campo.
    draft: dict[str, str | None]
    origins: dict[str, str]
    expires_at: datetime


def _context(organization_id: uuid.UUID, holder: str) -> str:
    # Amarrado à organização e a quem pediu a prévia (outro ADMIN não usa).
    return f"connect_ticket:{organization_id}:{holder}"


def issue_ticket(
    box: SecretBox,
    *,
    organization_id: uuid.UUID,
    holder: str,
    provider: str,
    credentials: ProviderLogin,
    serials: list[str],
    draft: dict[str, str | None],
    origins: dict[str, str],
    now: datetime | None = None,
) -> tuple[str, datetime]:
    expires_at = (now or datetime.now(UTC)) + TICKET_TTL
    payload = json.dumps(
        {
            "p": provider,
            "l": credentials.login,
            "s": credentials.password,
            "sr": serials,
            "d": draft,
            "o": origins,
            "e": expires_at.isoformat(),
        },
        separators=(",", ":"),
    ).encode()
    sealed = box.seal(payload, context=_context(organization_id, holder))
    encoded = base64.urlsafe_b64encode(sealed.ciphertext).decode().rstrip("=")
    ticket = f"v{sealed.key_version}.{encoded}"
    if len(ticket) > MAX_TICKET_CHARS:
        raise ConnectTicketError("ticket too large")
    return ticket, expires_at


def open_ticket(
    box: SecretBox,
    ticket: str,
    *,
    organization_id: uuid.UUID,
    holder: str,
    now: datetime | None = None,
) -> ConnectTicket:
    if not isinstance(ticket, str) or len(ticket) > MAX_TICKET_CHARS:
        raise ConnectTicketError("invalid ticket")
    version_text, dot, body = ticket.partition(".")
    if not dot or not version_text.startswith("v") or not version_text[1:].isdigit():
        raise ConnectTicketError("invalid ticket")
    try:
        ciphertext = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        raw = box.open(
            SealedSecret(ciphertext=ciphertext, key_version=int(version_text[1:])),
            context=_context(organization_id, holder),
        )
        data: dict[str, Any] = json.loads(raw)
        expires_at = datetime.fromisoformat(data["e"])
        result = ConnectTicket(
            provider=str(data["p"]),
            credentials=ProviderLogin(login=str(data["l"]), password=str(data["s"])),
            serials=[str(item) for item in data["sr"]],
            draft={str(k): (None if v is None else str(v)) for k, v in dict(data["d"]).items()},
            origins={str(k): str(v) for k, v in dict(data["o"]).items()},
            expires_at=expires_at,
        )
    except (SecretBoxError, binascii.Error, ValueError, KeyError, TypeError):
        raise ConnectTicketError("invalid ticket") from None
    if (now or datetime.now(UTC)) >= result.expires_at:
        raise ConnectTicketError("invalid ticket")
    return result
