from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Single instance — PasswordHasher is thread-safe and holds the param config.
_hasher = PasswordHasher()


def hash_password(raw: str) -> str:
    """Return an argon2id encoded hash of *raw*."""
    return _hasher.hash(raw)


def verify_password(raw: str, encoded: str) -> bool:
    """Return True if *raw* matches *encoded*, False otherwise. Never raises."""
    try:
        return _hasher.verify(encoded, raw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
