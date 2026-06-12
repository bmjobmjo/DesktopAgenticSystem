"""Security helpers for API gateway auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERS = 240_000


def hash_password(password: str) -> str:
    pwd = str(password or "")
    if not pwd:
        raise ValueError("Password cannot be empty")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, pwd.encode("utf-8"), salt, _PBKDF2_ITERS)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2${_PBKDF2_ITERS}${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    pwd = str(password or "")
    hashed = str(stored_hash or "")
    if not hashed or not pwd:
        return False

    # Backward compatibility fallback: literal compare for legacy plain-text values.
    if not hashed.startswith("pbkdf2$"):
        return hmac.compare_digest(pwd, hashed)

    try:
        _prefix, iter_s, salt_b64, digest_b64 = hashed.split("$", 3)
        iterations = int(iter_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, pwd.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def generate_temp_password(length: int = 14) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(max(10, int(length))))
