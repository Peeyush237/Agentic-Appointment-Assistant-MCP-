from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

TOKEN_TTL_DAYS = 30
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{salt}${digest}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        salt, digest = password_hash.split("$", 1)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return safe_compare(candidate, digest)


def generate_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def token_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=TOKEN_TTL_DAYS)
