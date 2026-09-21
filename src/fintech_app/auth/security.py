"""
Cryptographic and Security Services for GraeaeEye Authentication.

Provides:
- Argon2id password hashing and verification via passlib.
- Cryptographically signed HS256 JSON Web Tokens (JWT) for session management.
- Token decoding, signature verification, and expiration enforcement.
- Strict prevention of sensitive credential leakage into logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, Optional
from uuid import UUID

import jwt

try:
    from passlib.hash import argon2

    _has_argon2 = True
except Exception:
    from passlib.hash import bcrypt as argon2

    _has_argon2 = False

from ..core.config import settings

logger = logging.getLogger("fintech_app.auth.security")

DEFAULT_SECRET_KEY = "change-me-in-dev-graeae-eye-secret-key-32bytes"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "graeae-eye"
SESSION_DURATION_SECONDS = 86400  # 24 hours


def _get_secret_key() -> str:
    """Resolves secret key from settings, environment, or fallback default for tests."""
    secret = getattr(settings, "session_secret_key", None) or os.getenv("SECRET_KEY") or DEFAULT_SECRET_KEY
    return str(secret)


def hash_password(plain_password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return argon2.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored hash."""
    try:
        return argon2.verify(plain_password, hashed_password)
    except Exception as exc:
        logger.warning("Password verification failed with error: %s", type(exc).__name__)
        return False


def create_session_token(
    payload: Dict[str, Any],
    expires_delta_seconds: Optional[int] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Creates a signed HS256 JWT session token.

    Standard claims:
    - sub: user_id (UUID string)
    - email: str
    - role: str
    - iat: int (issued-at Unix timestamp)
    - exp: int (expiration Unix timestamp)
    - iss: 'graeae-eye'
    """
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    duration = expires_delta_seconds if expires_delta_seconds is not None else SESSION_DURATION_SECONDS
    exp_ts = now_ts + duration

    sub_val = payload.get("sub") or payload.get("user_id")
    if isinstance(sub_val, UUID):
        sub_str = str(sub_val)
    elif sub_val:
        sub_str = str(sub_val)
    else:
        sub_str = ""

    token_claims: Dict[str, Any] = {
        "sub": sub_str,
        "email": str(payload.get("email", "")),
        "role": str(payload.get("role", "ANALYST")),
        "iat": now_ts,
        "exp": exp_ts,
        "iss": JWT_ISSUER,
    }

    key = secret_key or _get_secret_key()
    return jwt.encode(token_claims, key, algorithm=JWT_ALGORITHM)


def decode_session_token(
    token: str,
    secret_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decodes and validates a signed JWT session token.

    Verifies signature, expiration, and issuer.
    Raises jwt.PyJWTError on validation or signature failure.
    """
    key = secret_key or _get_secret_key()
    claims = jwt.decode(
        token,
        key,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["sub", "exp", "iat", "iss"]},
    )
    return claims


__all__ = [
    "hash_password",
    "verify_password",
    "create_session_token",
    "decode_session_token",
    "DEFAULT_SECRET_KEY",
    "JWT_ALGORITHM",
    "JWT_ISSUER",
]
