"""
Password hashing and JWT helpers.

This module deliberately has no FastAPI imports, so it is easy to unit-test
and could be reused by any Python program.

Password hashing: PBKDF2-HMAC-SHA256 from Python's standard library.
  * A random 16-byte salt per password stops rainbow-table attacks and makes
    two users with the same password get different hashes.
  * Many iterations (600,000 by default, OWASP's current recommendation for
    PBKDF2-SHA256) make brute-forcing a stolen hash slow.
  * The iteration count and salt are stored inside the hash string, so we can
    raise the iteration count later without breaking old passwords.
  * hmac.compare_digest compares in constant time to avoid timing attacks.

JWT: a signed token that says "user X with role Y, valid until Z". Any service
that knows the secret can verify it locally, without calling the User Service.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

HASH_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16


class TokenError(Exception):
    """Raised when a JWT is missing, expired, tampered with or malformed."""


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Return a string like 'pbkdf2_sha256$600000$<salt>$<hash>'."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{HASH_SCHEME}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a plain-text password against a stored hash. Never raises."""
    try:
        scheme, iterations_text, salt_text, digest_text = stored_hash.split("$")
        if scheme != HASH_SCHEME:
            return False
        iterations = int(iterations_text)
        if iterations < 1:
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
    except (ValueError, AttributeError, binascii.Error):
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def create_access_token(
    *,
    user_id: str,
    role: str,
    email: str,
    full_name: str,
    secret_key: str,
    algorithm: str = "HS256",
    expires_minutes: int = 60,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,  # "subject": who the token is about
        "role": role,
        "email": email,
        "name": full_name,
        "iat": now,  # issued at
        "exp": now + timedelta(minutes=expires_minutes),  # expiry, checked by PyJWT
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(token: str, *, secret_key: str, algorithm: str = "HS256") -> dict[str, Any]:
    """Verify the signature and expiry, then return the token's claims."""
    try:
        return jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],  # explicit allow-list prevents algorithm-swap attacks
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired. Please log in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid authentication token.") from exc
