"""
API Dependencies for FastAPI routes.

Provides:
- Database abstraction layer (DAL) dependency injection (get_db).
- Session token authentication (get_current_user) via JWT decoding and DAL lookup.
- Fallback mock principal when USE_MOCK_ENGINE=true or database is absent.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Generator, Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
import jwt

try:
    from fintech_app.api.schemas import CurrentUser
    from fintech_app.auth.security import decode_session_token
    from fintech_app.core.config import settings
except ModuleNotFoundError:
    from src.fintech_app.api.schemas import CurrentUser
    from src.fintech_app.auth.security import decode_session_token
    from src.fintech_app.core.config import settings

logger = logging.getLogger("fintech_app.api.dependencies")

MOCK_USER_PRINCIPAL = CurrentUser(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    email="analyst@graeae.eye",
    full_name="Graeae Senior Underwriter",
    role="ANALYST",
)


def get_db_connection() -> Generator[Any, None, None]:
    """Database connection generator yielding active database instance."""
    if not settings.use_mock_engine:
        try:
            from fintech_app.db.connection import Database

            yield Database.get_instance()
            return
        except Exception:
            pass
    try:
        from fintech_app.db.mock_connection import MockDatabase

        yield MockDatabase.get_instance()
    except Exception:
        yield None


async def get_db(request: Request) -> AsyncGenerator[Optional[object], None]:
    """
    Yields the active Database / MockDatabase instance if available, or None.

    Defensive against missing database layer, connection failures, or offline mock mode.
    """
    if hasattr(request, "app") and hasattr(request.app, "state") and hasattr(request.app.state, "db"):
        yield request.app.state.db
        return

    db = None
    try:
        from fintech_app.main import db_pool

        db = db_pool
    except Exception:
        db = None

    if db is None and not settings.use_mock_engine:
        try:
            from fintech_app.db.connection import Database

            db = Database.get_instance()
        except Exception as exc:
            logger.warning("Could not acquire Database instance in get_db: %s", exc)
            db = None

    yield db


async def get_current_user(request: Request) -> CurrentUser:
    """
    Authenticates the incoming request via secure HttpOnly session cookie or Bearer header.

    - Reads 'session_token' cookie or 'Authorization: Bearer <token>' header. Missing -> 401 UNAUTHORIZED.
    - If db is None or settings.use_mock_engine: returns mock principal.
    - If db is present: validates JWT signature & expiration, queries users table by sub (UUID).
      Raises 401 UNAUTHORIZED on invalid token, expired token, or nonexistent user.
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header and auth_header.strip():
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                session_token = parts[1]
            elif len(parts) == 1:
                session_token = parts[0]

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Authentication credentials were not provided.", "code": "UNAUTHORIZED"},
        )

    db = None
    if hasattr(request, "app") and hasattr(request.app, "state"):
        db = getattr(request.app.state, "db", None)

    if db is None:
        try:
            from fintech_app.main import db_pool

            db = db_pool
        except Exception:
            db = None

    # Fallback to mock principal in mock mode or when database is unavailable
    if db is None or settings.use_mock_engine:
        return MOCK_USER_PRINCIPAL

    # Validate JWT session token
    try:
        payload = decode_session_token(session_token)
    except jwt.PyJWTError as jwt_err:
        logger.warning("Session token rejected: %s", type(jwt_err).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Invalid or expired session token.", "code": "UNAUTHORIZED"},
        )
    except Exception as exc:
        logger.warning("Unexpected error during session token decode: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Invalid or expired session token.", "code": "UNAUTHORIZED"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Invalid session token claims.", "code": "UNAUTHORIZED"},
        )

    try:
        user_uuid = UUID(str(sub))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Malformed user identifier in session token.", "code": "UNAUTHORIZED"},
        )

    # Query DAL users table to verify user existence and active status
    try:
        user_rep = await db.get_records_from_users(find_only_first=True, user_id=user_uuid)
    except Exception as db_exc:
        logger.error("Database query error in get_current_user: %s", db_exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Authentication verification failed.", "code": "UNAUTHORIZED"},
        )

    if not user_rep.success or not user_rep.data:
        logger.warning("Session rejected: user_id %s not found in DAL", user_uuid)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "User associated with session token does not exist.", "code": "UNAUTHORIZED"},
        )

    user = user_rep.data
    if not user.get("is_active", True):
        logger.warning("Session rejected: user_id %s is inactive", user_uuid)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "User account is inactive.", "code": "UNAUTHORIZED"},
        )

    return CurrentUser(
        user_id=UUID(str(user["user_id"])),
        email=str(user["email"]),
        full_name=str(user["full_name"]),
        role=str(user.get("role", "ANALYST")),
    )
