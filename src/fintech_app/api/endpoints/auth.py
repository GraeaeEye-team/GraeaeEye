"""
Authentication Endpoints for the GraeaeEye API (Phase 1).

Provides mock login and registration contracts setting secure session cookies.
No real Argon2/JWT signing in Phase 1 (deferred to Phase 2).
Tokens are strictly barred from response bodies and query strings (Rule P9).
"""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response, status

from fintech_app.api.schemas import (
    ErrorResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Deterministic mock user fixture for Phase 1 testing
MOCK_USER_FIXTURE = {
    "user_id": UUID("00000000-0000-0000-0000-000000000001"),
    "email": "analyst@graeae.eye",
    "password": "correct-horse-battery-staple",
    "full_name": "Graeae Senior Underwriter",
    "role": "ANALYST",
}

COOKIE_NAME = "session_token"
MOCK_SESSION_TOKEN = "mock-session-token-phase1-secret"


@router.post(
    "/token",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": UserResponse, "description": "Successfully authenticated session."},
        401: {"model": ErrorResponse, "description": "Invalid credentials."},
        422: {"model": ErrorResponse, "description": "Validation error."},
    },
    summary="User token authentication",
    description="Primary auth endpoint (Spec v2.0 §3.1). Authenticates user and attaches an HttpOnly, Secure session cookie.",
)
async def login(credentials: UserLoginRequest, response: Response) -> UserResponse:
    """Authenticates credentials against the mock fixture and issues an HttpOnly cookie."""
    # Strict exact-match validation against the mock fixture
    if (
        credentials.email != MOCK_USER_FIXTURE["email"]
        or credentials.password != MOCK_USER_FIXTURE["password"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
        )

    logger.info("User login successful for email '%s'", credentials.email)

    # Set secure session cookie per Rule P9 (HttpOnly; Secure; SameSite=Lax)
    response.set_cookie(
        key=COOKIE_NAME,
        value=MOCK_SESSION_TOKEN,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    return UserResponse(
        user_id=MOCK_USER_FIXTURE["user_id"],
        email=credentials.email,
        full_name=MOCK_USER_FIXTURE["full_name"],
        role=MOCK_USER_FIXTURE["role"],
        is_active=True,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": UserResponse, "description": "User account created."},
        422: {"model": ErrorResponse, "description": "Validation error."},
    },
    summary="User registration",
    description="Registers a new user and attaches an HttpOnly, Secure session cookie.",
)
async def register(payload: UserRegisterRequest, response: Response) -> UserResponse:
    """Creates a user account stub in Phase 1 and establishes a session cookie."""
    new_user_id = uuid4()
    logger.info("User registered with email '%s'", payload.email)

    response.set_cookie(
        key=COOKIE_NAME,
        value=MOCK_SESSION_TOKEN,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    return UserResponse(
        user_id=new_user_id,
        email=payload.email,
        full_name=payload.full_name,
        role="ANALYST",
        is_active=True,
    )
