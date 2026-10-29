"""Cofre de segredos recuperáveis (ADR-091).

Diferente da credencial de API (ADR-043, só hash), a senha do fabricante do
inversor precisa voltar a texto claro para entrar na API dele. Este módulo
cifra com AES-256-GCM e amarra cada texto cifrado a um contexto (AAD): o
chamador passa, por exemplo, ``provider_account:<plant_id>:NEPVIEWER``, e o
mesmo texto cifrado copiado para outra usina não decifra.

A chave nunca fica no banco. Vem de ``MPLACAS_PROVIDER_SECRET_KEYS`` no
formato ``1:<base64 de 32 bytes>,2:<...>``: a versão de maior número cifra;
as demais só decifram, o que permite trocar a chave e recifrar aos poucos.

Nenhuma mensagem de erro, ``repr`` ou log deste módulo contém chave, texto
claro ou texto cifrado.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_BYTES = 32
NONCE_BYTES = 12
_FINGERPRINT_INFO = b"mplacas:secret-box:fingerprint:v1"


class SecretBoxError(Exception):
    """Base dos erros do cofre. Mensagens nunca carregam material secreto."""


class SecretBoxUnavailableError(SecretBoxError):
    """Chave ausente ou mal formada: o cofre falha fechado."""


class SecretBoxDecryptError(SecretBoxError):
    """Texto cifrado adulterado, de outro contexto ou de chave desconhecida."""


@dataclass(frozen=True, slots=True)
class SealedSecret:
    """Texto cifrado (nonce + cifra + tag) e a versão da chave que o produziu."""

    ciphertext: bytes
    key_version: int

    def __repr__(self) -> str:
        size = len(self.ciphertext)
        return f"SealedSecret(key_version={self.key_version}, ciphertext=<{size} bytes>)"


def _check_label(value: str, *, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SecretBoxError(f"secret box {name} is required")
    if "\x00" in value:
        raise SecretBoxError(f"secret box {name} must not contain NUL")


def _associated_data(context: str, key_version: int) -> bytes:
    # Campos separados por NUL (proibido no contexto): a codificação é
    # injetiva, então nenhum par (contexto, versão) imita outro.
    _check_label(context, name="context")
    return b"\x00".join((b"mplacas-secret-box", str(key_version).encode(), context.encode()))


def parse_keyring(raw: str) -> dict[int, bytes]:
    """Lê ``1:<base64>,2:<base64>``. Erros não repetem o valor recebido."""
    keys: dict[int, bytes] = {}
    for position, item in enumerate(raw.split(","), start=1):
        item = item.strip()
        if not item:
            continue
        version_text, separator, encoded = item.partition(":")
        if not separator:
            raise SecretBoxUnavailableError(
                f"provider secret keyring entry {position} must be '<version>:<base64>'"
            )
        version_text = version_text.strip()
        if not (version_text.isascii() and version_text.isdecimal()):
            raise SecretBoxUnavailableError(
                f"provider secret keyring entry {position} has a non-numeric version"
            )
        version = int(version_text)
        if version < 1:
            raise SecretBoxUnavailableError(
                f"provider secret keyring entry {position} must have a version >= 1"
            )
        if version in keys:
            raise SecretBoxUnavailableError(f"provider secret keyring repeats version {version}")
        try:
            key = base64.b64decode(encoded.strip(), validate=True)
        except (binascii.Error, ValueError):
            raise SecretBoxUnavailableError(
                f"provider secret keyring entry {position} is not valid base64"
            ) from None
        if len(key) != KEY_BYTES:
            raise SecretBoxUnavailableError(
                f"provider secret keyring entry {position} must decode to {KEY_BYTES} bytes"
            )
        keys[version] = key
    if not keys:
        raise SecretBoxUnavailableError("provider secret keyring is empty")
    return keys


class SecretBox:
    """Cifra e decifra segredos com AES-256-GCM e um chaveiro versionado."""

    __slots__ = ("_ciphers", "_current_version", "_fingerprint_key")

    def __init__(self, keys: Mapping[int, bytes]) -> None:
        if not keys:
            raise SecretBoxUnavailableError("provider secret keyring is empty")
        for version, key in keys.items():
            if version < 1 or len(key) != KEY_BYTES:
                raise SecretBoxUnavailableError(f"provider secret key version {version} is invalid")
        self._current_version = max(keys)
        self._ciphers = {version: AESGCM(key) for version, key in keys.items()}
        self._fingerprint_key = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=None,
            info=_FINGERPRINT_INFO,
        ).derive(keys[self._current_version])

    @classmethod
    def from_keyring(cls, raw: str) -> SecretBox:
        return cls(parse_keyring(raw))

    @property
    def current_version(self) -> int:
        return self._current_version

    def __repr__(self) -> str:
        versions = sorted(self._ciphers)
        return f"SecretBox(current_version={self._current_version}, versions={versions})"

    def seal(self, plaintext: bytes, *, context: str) -> SealedSecret:
        if not isinstance(plaintext, bytes):
            raise SecretBoxError("secret box plaintext must be bytes")
        version = self._current_version
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = self._ciphers[version].encrypt(
            nonce, plaintext, _associated_data(context, version)
        )
        return SealedSecret(ciphertext=nonce + ciphertext, key_version=version)

    def open(self, sealed: SealedSecret, *, context: str) -> bytes:
        if type(sealed.key_version) is not int:
            raise SecretBoxDecryptError("provider secret key version is invalid")
        cipher = self._ciphers.get(sealed.key_version)
        if cipher is None:
            raise SecretBoxDecryptError(f"no provider secret key for version {sealed.key_version}")
        if len(sealed.ciphertext) <= NONCE_BYTES:
            raise SecretBoxDecryptError("provider secret ciphertext is truncated")
        nonce = sealed.ciphertext[:NONCE_BYTES]
        try:
            return cipher.decrypt(
                nonce,
                sealed.ciphertext[NONCE_BYTES:],
                _associated_data(context, sealed.key_version),
            )
        except InvalidTag:
            raise SecretBoxDecryptError(
                "provider secret could not be decrypted for this context"
            ) from None

    def needs_rotation(self, sealed: SealedSecret) -> bool:
        return sealed.key_version != self._current_version

    def rotate(self, sealed: SealedSecret, *, context: str) -> SealedSecret:
        """Recifra com a chave atual, preservando o contexto."""
        return self.seal(self.open(sealed, context=context), context=context)

    def fingerprint(self, value: str, *, purpose: str) -> str:
        """HMAC-SHA256 estável para detectar repetição sem guardar o valor.

        Usa uma subchave derivada (HKDF) da chave atual, nunca a chave de
        cifra diretamente. Trocar a chave muda as impressões: o comando de
        rotação as recalcula junto com o texto cifrado.
        """
        _check_label(purpose, name="fingerprint purpose")
        message = f"{purpose}\x00{value}".encode()
        return hmac.new(self._fingerprint_key, message, hashlib.sha256).hexdigest()


def generate_key() -> str:
    """Gera uma chave nova em base64, para montar o chaveiro."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def secret_box_from_keyring(raw: str | None) -> SecretBox:
    if raw is None or not raw.strip():
        raise SecretBoxUnavailableError("MPLACAS_PROVIDER_SECRET_KEYS is not configured")
    return SecretBox.from_keyring(raw)


@lru_cache(maxsize=4)
def _cached_box(raw: str) -> SecretBox:
    return SecretBox.from_keyring(raw)


def secret_box_from_settings() -> SecretBox:
    """Cofre da configuração atual; reaproveitado enquanto o chaveiro não muda."""
    from mplacas.core.config import get_settings

    configured = get_settings().provider_secret_keys
    raw = configured.get_secret_value() if configured is not None else None
    if raw is None or not raw.strip():
        raise SecretBoxUnavailableError("MPLACAS_PROVIDER_SECRET_KEYS is not configured")
    return _cached_box(raw)


if __name__ == "__main__":  # pragma: no cover - ajuda operacional
    # ``python -m mplacas.core.secret_box`` imprime uma entrada nova para o
    # chaveiro. Para trocar a chave, acrescente-a com a versão seguinte.
    print(f"1:{generate_key()}")
