from __future__ import annotations

import base64
import logging

import pytest

from mplacas.core.config import Settings
from mplacas.core.secret_box import (
    KEY_BYTES,
    NONCE_BYTES,
    SealedSecret,
    SecretBox,
    SecretBoxDecryptError,
    SecretBoxError,
    SecretBoxUnavailableError,
    generate_key,
    parse_keyring,
    secret_box_from_keyring,
)

KEY_1 = base64.b64encode(b"\x01" * KEY_BYTES).decode()
KEY_2 = base64.b64encode(b"\x02" * KEY_BYTES).decode()
CONTEXT_A = "provider_account:00000000-0000-0000-0000-00000000000a:NEPVIEWER"
CONTEXT_B = "provider_account:00000000-0000-0000-0000-00000000000b:NEPVIEWER"
SECRET = b'{"login":"cliente@example.com","password":"s3nh4-do-inversor"}'


def _box(raw: str = f"1:{KEY_1}") -> SecretBox:
    return SecretBox.from_keyring(raw)


def test_round_trip_returns_the_original_plaintext() -> None:
    box = _box()
    sealed = box.seal(SECRET, context=CONTEXT_A)

    assert sealed.key_version == 1
    assert SECRET not in sealed.ciphertext
    assert box.open(sealed, context=CONTEXT_A) == SECRET


def test_each_seal_uses_a_fresh_nonce() -> None:
    box = _box()
    first = box.seal(SECRET, context=CONTEXT_A)
    second = box.seal(SECRET, context=CONTEXT_A)

    assert first.ciphertext[:NONCE_BYTES] != second.ciphertext[:NONCE_BYTES]
    assert first.ciphertext != second.ciphertext


def test_ciphertext_copied_to_another_plant_does_not_decrypt() -> None:
    box = _box()
    sealed = box.seal(SECRET, context=CONTEXT_A)

    with pytest.raises(SecretBoxDecryptError):
        box.open(sealed, context=CONTEXT_B)


def test_tampered_ciphertext_does_not_decrypt() -> None:
    box = _box()
    sealed = box.seal(SECRET, context=CONTEXT_A)
    flipped = bytearray(sealed.ciphertext)
    flipped[-1] ^= 0x01

    with pytest.raises(SecretBoxDecryptError):
        box.open(SealedSecret(bytes(flipped), sealed.key_version), context=CONTEXT_A)


def test_relabelled_key_version_does_not_decrypt() -> None:
    """A versão entra no AAD: trocar o rótulo não engana a verificação."""
    box = SecretBox({1: b"\x01" * KEY_BYTES, 2: b"\x01" * KEY_BYTES})
    sealed = box.seal(SECRET, context=CONTEXT_A)

    with pytest.raises(SecretBoxDecryptError):
        box.open(SealedSecret(sealed.ciphertext, 1), context=CONTEXT_A)


def test_truncated_ciphertext_fails_closed() -> None:
    with pytest.raises(SecretBoxDecryptError):
        _box().open(SealedSecret(b"\x00" * NONCE_BYTES, 1), context=CONTEXT_A)


def test_highest_version_encrypts_and_older_versions_still_decrypt() -> None:
    old_box = _box(f"1:{KEY_1}")
    sealed_with_old_key = old_box.seal(SECRET, context=CONTEXT_A)

    new_box = _box(f"1:{KEY_1},2:{KEY_2}")

    assert new_box.current_version == 2
    assert new_box.needs_rotation(sealed_with_old_key)
    assert new_box.open(sealed_with_old_key, context=CONTEXT_A) == SECRET

    rotated = new_box.rotate(sealed_with_old_key, context=CONTEXT_A)
    assert rotated.key_version == 2
    assert not new_box.needs_rotation(rotated)
    assert _box(f"2:{KEY_2}").open(rotated, context=CONTEXT_A) == SECRET


def test_unknown_key_version_fails_closed() -> None:
    sealed = _box(f"2:{KEY_2}").seal(SECRET, context=CONTEXT_A)

    with pytest.raises(SecretBoxDecryptError, match="version 2"):
        _box(f"1:{KEY_1}").open(sealed, context=CONTEXT_A)


def test_empty_context_is_rejected() -> None:
    with pytest.raises(SecretBoxError):
        _box().seal(SECRET, context=" ")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        f"{KEY_1}",
        f"x:{KEY_1}",
        f"0:{KEY_1}",
        "1:not-base64!!",
        f"1:{base64.b64encode(b'short').decode()}",
        f"1:{KEY_1},1:{KEY_2}",
    ],
)
def test_malformed_keyring_fails_closed_without_echoing_the_value(raw: str) -> None:
    with pytest.raises(SecretBoxUnavailableError) as raised:
        secret_box_from_keyring(raw)

    message = str(raised.value)
    assert KEY_1 not in message
    assert KEY_2 not in message
    assert "not-base64" not in message


def test_missing_keyring_fails_closed() -> None:
    with pytest.raises(SecretBoxUnavailableError, match="not configured"):
        secret_box_from_keyring(None)


def test_keyring_tolerates_spaces_and_trailing_comma() -> None:
    keys = parse_keyring(f" 1 : {KEY_1} , 2:{KEY_2},")

    assert sorted(keys) == [1, 2]


def test_fingerprint_is_stable_and_never_the_raw_value() -> None:
    box = _box()

    first = box.fingerprint("cliente@example.com", purpose="NEPVIEWER")
    second = box.fingerprint("cliente@example.com", purpose="NEPVIEWER")

    assert first == second
    assert len(first) == 64
    assert "cliente" not in first
    assert first != box.fingerprint("outro@example.com", purpose="NEPVIEWER")
    assert first != box.fingerprint("cliente@example.com", purpose="SOLIS")


def test_fingerprint_changes_with_the_current_key() -> None:
    value = "cliente@example.com"

    assert _box(f"1:{KEY_1}").fingerprint(value, purpose="NEPVIEWER") != _box(
        f"1:{KEY_1},2:{KEY_2}"
    ).fingerprint(value, purpose="NEPVIEWER")


def test_repr_and_logs_never_carry_secret_material(caplog: pytest.LogCaptureFixture) -> None:
    box = _box(f"1:{KEY_1},2:{KEY_2}")
    sealed = box.seal(SECRET, context=CONTEXT_A)

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("test").info("box=%r sealed=%r", box, sealed)

    rendered = repr(box) + repr(sealed) + caplog.text
    for forbidden in (KEY_1, KEY_2, "s3nh4", "cliente@example.com"):
        assert forbidden not in rendered
    assert sealed.ciphertext.hex() not in rendered


def test_generated_keys_are_valid_and_distinct() -> None:
    first, second = generate_key(), generate_key()

    assert first != second
    assert _box(f"1:{first}").current_version == 1


def test_settings_keep_the_keyring_secret() -> None:
    settings = Settings(provider_secret_keys=f"1:{KEY_1}")

    assert KEY_1 not in repr(settings)
    assert KEY_1 not in str(settings.safe_summary())
    assert settings.safe_summary()["provider_secret_keys_configured"] is True
    assert Settings().safe_summary()["provider_secret_keys_configured"] is False


def test_empty_plaintext_round_trips() -> None:
    box = _box()

    assert box.open(box.seal(b"", context=CONTEXT_A), context=CONTEXT_A) == b""


def test_tampered_nonce_does_not_decrypt() -> None:
    box = _box()
    sealed = box.seal(SECRET, context=CONTEXT_A)
    flipped = bytearray(sealed.ciphertext)
    flipped[0] ^= 0x01

    with pytest.raises(SecretBoxDecryptError):
        box.open(SealedSecret(bytes(flipped), sealed.key_version), context=CONTEXT_A)


def test_rotate_with_the_wrong_context_fails_closed() -> None:
    sealed = _box(f"1:{KEY_1}").seal(SECRET, context=CONTEXT_A)

    with pytest.raises(SecretBoxDecryptError):
        _box(f"1:{KEY_1},2:{KEY_2}").rotate(sealed, context=CONTEXT_B)


@pytest.mark.parametrize("context", ["a\x00b", ""])
def test_ambiguous_contexts_are_rejected(context: str) -> None:
    with pytest.raises(SecretBoxError):
        _box().seal(SECRET, context=context)


def test_non_bytes_plaintext_raises_a_secret_box_error() -> None:
    with pytest.raises(SecretBoxError):
        _box().seal("texto", context=CONTEXT_A)  # type: ignore[arg-type]


def test_non_integer_key_version_fails_closed() -> None:
    sealed = _box().seal(SECRET, context=CONTEXT_A)

    with pytest.raises(SecretBoxDecryptError):
        _box().open(SealedSecret(sealed.ciphertext, True), context=CONTEXT_A)


@pytest.mark.parametrize("version", ["+1", "1_0", "١"])
def test_keyring_versions_must_be_plain_ascii_digits(version: str) -> None:
    with pytest.raises(SecretBoxUnavailableError):
        parse_keyring(f"{version}:{KEY_1}")


def test_settings_read_the_keyring_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mplacas.core.config import get_settings
    from mplacas.core.secret_box import secret_box_from_settings

    monkeypatch.setenv("MPLACAS_PROVIDER_SECRET_KEYS", f"1:{KEY_1},2:{KEY_2}")
    get_settings.cache_clear()
    try:
        box = secret_box_from_settings()
        assert box.current_version == 2
        assert secret_box_from_settings() is box
    finally:
        get_settings.cache_clear()


def test_settings_without_keyring_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from mplacas.core.config import get_settings
    from mplacas.core.secret_box import secret_box_from_settings

    monkeypatch.delenv("MPLACAS_PROVIDER_SECRET_KEYS", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(SecretBoxUnavailableError):
            secret_box_from_settings()
    finally:
        get_settings.cache_clear()
