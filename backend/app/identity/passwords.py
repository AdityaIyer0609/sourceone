"""Password hashes. The stored value is never sent to clients."""

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ROUNDS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ROUNDS)
    return f"{_ALGO}${_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, rounds, salt_hex, digest_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
