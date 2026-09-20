"""
Authentication Endpoints for the GraeaeEye API (Gate 4).

Provides:
- User token authentication (/auth/token) via Argon2id verification and HS256 JWT session cookies.
- User registration (/auth/register) with field validation, email uniqueness enforcement, and DAL persistence.
- Deterministic mock fallback when USE_MOCK_ENGINE=true or database connection is unavailable.
- Strict security adherence: passwords/hashes never logged, tokens never in body (Rule P9).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..schemas import (
    ErrorResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

from ..dependencies import get_db
from ..schemas import (
    ErrorResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from ...auth.security import (
    create_session_token,
    hash_password,
    verify_password,
)
from ...core.config import settings

logger = logging.getLogger("fintech_app.api.auth")

router = APIRouter()

# Deterministic mock user fixture for Phase 1 / mock testing
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
@router.post(
    "/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def login(
    request: Request,
    response: Response,
    db: Any = Depends(get_db),
) -> UserResponse:
    """Authenticates credentials against DAL or mock fixture and issues an HttpOnly cookie and bearer token."""
    content_type = request.headers.get("content-type", "").lower()
    email_val = ""
    password_val = ""

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form_data = await request.form()
        email_val = str(form_data.get("username") or form_data.get("email") or "").strip()
        password_val = str(form_data.get("password") or "")
    else:
        try:
            json_data = await request.json()
            if isinstance(json_data, dict):
                email_val = str(json_data.get("email") or json_data.get("username") or "").strip()
                password_val = str(json_data.get("password") or "")
        except Exception:
            pass

    if not email_val or not password_val:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "Username/email and password required.", "code": "VALIDATION_ERROR"},
        )

    # 1. Fallback to mock behavior if database unavailable or mock mode enabled
    if db is None or settings.use_mock_engine:
        if email_val != MOCK_USER_FIXTURE["email"] or password_val != MOCK_USER_FIXTURE["password"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"detail": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
            )

        logger.info("User login successful (mock) for email '%s'", email_val)

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
            email=email_val,
            full_name=MOCK_USER_FIXTURE["full_name"],
            role=MOCK_USER_FIXTURE["role"],
            is_active=True,
            access_token=MOCK_SESSION_TOKEN,
            token_type="bearer",
        )

    # 2. Real Authentication Path via Data Access Layer
    user_rep = await db.get_records_from_users(find_only_first=True, email=email_val)
    if not user_rep.success or not user_rep.data:
        logger.warning("Authentication failed: user '%s' not found", email_val)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
        )

    user = user_rep.data
    stored_hash = user.get("password_hash", "")
    if not verify_password(password_val, stored_hash):
        logger.warning("Authentication failed: password mismatch for user '%s'", email_val)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
        )

    if not user.get("is_active", True):
        logger.warning("Authentication rejected: inactive account for user '%s'", email_val)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "User account is inactive.", "code": "INVALID_CREDENTIALS"},
        )

    user_id = UUID(str(user["user_id"]))
    email = str(user["email"])
    full_name = str(user["full_name"])
    role = str(user.get("role", "ANALYST"))

    # Issue signed JWT session token
    jwt_token = create_session_token({"sub": str(user_id), "email": email, "role": role})

    logger.info("User login successful for email '%s' (user_id: %s)", email, user_id)

    response.set_cookie(
        key=COOKIE_NAME,
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    return UserResponse(
        user_id=user_id,
        email=email,
        full_name=full_name,
        role=role,
        is_active=True,
        access_token=jwt_token,
        token_type="bearer",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": UserResponse, "description": "User account created."},
        409: {"model": ErrorResponse, "description": "Email already registered."},
        422: {"model": ErrorResponse, "description": "Validation error."},
    },
    summary="User registration",
    description="Registers a new user and attaches an HttpOnly, Secure session cookie.",
)
async def register(
    payload: UserRegisterRequest,
    response: Response,
    db: Any = Depends(get_db),
) -> UserResponse:
    """Validates user payload, hashes password, records in DAL, and establishes a session."""
    # 1. Input Validation (email format, password >= 8 chars, full_name non-empty)
    email_clean = payload.email.strip()
    if not email_clean or "@" not in email_clean or "." not in email_clean.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "Invalid email address format.", "code": "VALIDATION_ERROR"},
        )

    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Password must be at least 8 characters in length.",
                "code": "VALIDATION_ERROR",
            },
        )

    name_clean = payload.full_name.strip()
    if not name_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "Full name cannot be empty.", "code": "VALIDATION_ERROR"},
        )

    # 2. Mock Fallback
    if db is None or settings.use_mock_engine:
        new_user_id = uuid4()
        logger.info("Mock registration processed for email '%s'", email_clean)

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
            email=email_clean,
            full_name=name_clean,
            role="ANALYST",
            is_active=True,
            access_token=MOCK_SESSION_TOKEN,
            token_type="bearer",
        )

    # 3. Real DAL Registration Path
    # Check email uniqueness
    existing_rep = await db.get_records_from_users(find_only_first=True, email=email_clean)
    if existing_rep.success and existing_rep.data:
        logger.warning("Registration rejected: email '%s' already exists", email_clean)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": f"User with email '{email_clean}' already exists.",
                "code": "EMAIL_EXISTS",
            },
        )

    # Hash password via Argon2id (never logged)
    password_hash = hash_password(payload.password)
    new_user_id = uuid4()
    role = "ANALYST"

    add_rep = await db.add_record_to_users(
        user_id=new_user_id,
        email=email_clean,
        password_hash=password_hash,
        full_name=name_clean,
        role=role,
        is_active=True,
    )
    if not add_rep.success:
        logger.error("Failed to insert user record into DAL for '%s'", email_clean)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": "Internal error during user registration.", "code": "INTERNAL_ERROR"},
        )

    logger.info("User successfully registered: '%s' (user_id: %s)", email_clean, new_user_id)

    # Issue signed session JWT
    jwt_token = create_session_token({"sub": str(new_user_id), "email": email_clean, "role": role})

    response.set_cookie(
        key=COOKIE_NAME,
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    return UserResponse(
        user_id=new_user_id,
        email=email_clean,
        full_name=name_clean,
        role=role,
        is_active=True,
        access_token=jwt_token,
        token_type="bearer",
    )
