"""Signed login tokens. The payload is the user id and an expiry, not a permission list."""

import base64
import hashlib
import hmac
import json
import time
import uuid

from app.core.config import get_settings
from app.core.errors import NotAuthenticated


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def issue_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(
        {"sub": str(user_id), "iat": now, "exp": now + settings.auth_token_ttl_seconds},
        separators=(",", ":"),
    ).encode())
    signing = f"{header}.{body}".encode()
    signature = hmac.new(settings.auth_secret.get_secret_value().encode(), signing, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def read_user_id(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        header, body, signature = token.split(".")
        signing = f"{header}.{body}".encode()
        expected = hmac.new(settings.auth_secret.get_secret_value().encode(), signing, hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(signature), expected):
            raise NotAuthenticated("Sign in to continue.")
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < int(time.time()):
            raise NotAuthenticated("Sign in to continue.")
        return uuid.UUID(payload["sub"])
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise NotAuthenticated("Sign in to continue.") from error
