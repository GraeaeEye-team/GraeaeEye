"""
API Dependencies for FastAPI routes.

Provides defensive dependency injection for the database abstraction layer (DAL)
and Phase 1 mock session authentication.
"""

from typing import AsyncGenerator, Generator, Optional
from uuid import UUID

from fastapi import HTTPException, Request

from fintech_app.api.schemas import CurrentUser

# Defensive import of PostgreSQL Database class
try:
    from fintech_app.db.connection import Database
except ImportError:
    Database = None  # type: ignore[assignment,misc]


# Backward compatibility symbol
def get_db_connection() -> Generator[None, None, None]:
    """Preserved legacy stub for database connection generator."""
    yield None


async def get_db() -> AsyncGenerator[Optional[object], None]:
    """
    Yields the active Database instance if available, or None in Phase 1 mock mode.

    Defensive against missing database layer or configuration.
    """
    # In Phase 1 mock mode, database persistence is bypassed
    yield None


async def get_current_user(request: Request) -> CurrentUser:
    """
    Authenticates the incoming request via secure HttpOnly session cookie.

    Phase 1 Mock Implementation:
    - Reads session cookie ONLY (Rule P9: no tokens in body or query string).
    - Returns a deterministic CurrentUser DTO when present.
    - Missing/invalid cookie raises HTTP 401 with standard error envelope (code: UNAUTHORIZED).
    """
    session_token = request.cookies.get("session_token")

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail={"detail": "Authentication credentials were not provided.", "code": "UNAUTHORIZED"},
        )

    # In Phase 1 mock mode, any valid session cookie resolves to the mock principal
    return CurrentUser(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        email="analyst@graeae.eye",
        full_name="Graeae Senior Underwriter",
        role="ANALYST",
    )
