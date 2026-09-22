"""
Gate 4: Real Auth & Register over DAL In-Process Verification Tests.

Validates:
A. Real Register: POST /auth/register -> 201 + UserResponse; duplicate email -> 409 EMAIL_EXISTS;
   validation errors (short password, bad email, empty name) -> 422 VALIDATION_ERROR.
B. Real Token: POST /auth/token with matching creds -> 200 + Set-Cookie (JWT);
   wrong password -> 401 INVALID_CREDENTIALS; nonexistent email -> 401 INVALID_CREDENTIALS.
C. Session Validation: GET /api/v1/health -> 200 (public);
   GET /api/v1/analysis/stream/<uuid> with valid cookie -> 404 (not 401); without cookie -> 401.
D. Mock Fallback: USE_MOCK_ENGINE=true preserves existing behavior with fixture credentials.
E. Token Expiry & Tampering: expired or corrupted JWT in cookie -> 401 UNAUTHORIZED.
F. Security: response body never contains password_hash; plaintext passwords never logged.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.auth.security import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)
from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.main import app


# =====================================================================
# IN-PROCESS ASGI TEST HARNESS
# =====================================================================


async def asgi_call(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> Tuple[int, List[Tuple[str, str]], bytes]:
    """Pure in-process ASGI caller for FastAPI app."""
    headers = headers or {}
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    if body and not any(k.lower() == "content-length" for k in headers):
        raw_headers.append((b"content-length", str(len(body)).encode("latin-1")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
        "app": app,
    }
    status_code = None
    response_headers = []
    response_body = []
    sent = False
    disconnect_event = asyncio.Event()

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnect_event.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status_code, response_headers, response_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in message["headers"]]
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    return status_code, response_headers, b"".join(response_body)


def extract_cookie(headers: List[Tuple[str, str]], cookie_name: str) -> Optional[str]:
    """Extracts cookie value and attributes from response headers."""
    for k, v in headers:
        if k.lower() == "set-cookie":
            parts = v.split(";")
            first_part = parts[0].strip()
            if first_part.startswith(f"{cookie_name}="):
                return first_part[len(f"{cookie_name}=") :]
    return None


def get_set_cookie_header(headers: List[Tuple[str, str]], cookie_name: str) -> Optional[str]:
    """Returns raw Set-Cookie header string containing cookie_name."""
    for k, v in headers:
        if k.lower() == "set-cookie" and f"{cookie_name}=" in v:
            return v
    return None


# =====================================================================
# TEST A: REAL USER REGISTRATION OVER DAL
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_real_registration():
    """
    Test A: Validates user registration via POST /api/v1/auth/register:
    - 201 Created with UserResponse (no password hash)
    - Set-Cookie with signed JWT (HttpOnly, Secure, SameSite=Lax)
    - Duplicate email rejection -> 409 EMAIL_EXISTS
    - Field validation failures -> 422 VALIDATION_ERROR
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    payload = {
        "email": "new.underwriter@graeae.eye",
        "password": "secure-password-2026",
        "full_name": "Elena Rostova",
    }
    body = json.dumps(payload).encode("utf-8")

    # 1. Successful registration
    st, hdrs, resp_b = await asgi_call(
        "POST",
        "/api/v1/auth/register",
        {"content-type": "application/json"},
        body,
    )
    assert st == 201, f"Expected 201, got {st}: {resp_b.decode('utf-8')}"
    resp_data = json.loads(resp_b.decode("utf-8"))
    assert resp_data["email"] == payload["email"]
    assert resp_data["full_name"] == payload["full_name"]
    assert resp_data["role"] == "ANALYST"
    assert "password_hash" not in resp_data
    assert "password" not in resp_data

    # Cookie verified
    raw_cookie_hdr = get_set_cookie_header(hdrs, "session_token")
    assert raw_cookie_hdr is not None
    assert "HttpOnly" in raw_cookie_hdr
    assert "SameSite=lax" in raw_cookie_hdr or "SameSite=Lax" in raw_cookie_hdr
    token_val = extract_cookie(hdrs, "session_token")
    assert token_val is not None

    # Verify user persisted in MockDatabase with hashed password
    user_rep = await mock_db.get_records_from_users(find_only_first=True, email=payload["email"])
    assert user_rep.success and user_rep.data
    db_user = user_rep.data
    assert db_user["email"] == payload["email"]
    assert db_user["password_hash"] != payload["password"]
    assert verify_password(payload["password"], db_user["password_hash"])

    # 2. Duplicate registration -> 409 EMAIL_EXISTS
    st_dup, _, resp_dup_b = await asgi_call(
        "POST",
        "/api/v1/auth/register",
        {"content-type": "application/json"},
        body,
    )
    assert st_dup == 409
    dup_data = json.loads(resp_dup_b.decode("utf-8"))
    assert dup_data.get("code") == "EMAIL_EXISTS"

    # 3. Validation failure: password too short (< 8 chars)
    short_pw_body = json.dumps(
        {
            "email": "short@graeae.eye",
            "password": "short",
            "full_name": "Shorty",
        }
    ).encode("utf-8")
    st_short, _, resp_short_b = await asgi_call(
        "POST",
        "/api/v1/auth/register",
        {"content-type": "application/json"},
        short_pw_body,
    )
    assert st_short == 422
    short_data = json.loads(resp_short_b.decode("utf-8"))
    assert short_data.get("code") == "VALIDATION_ERROR"

    # 4. Validation failure: bad email
    bad_email_body = json.dumps(
        {
            "email": "notanemail",
            "password": "valid-password-123",
            "full_name": "No Email",
        }
    ).encode("utf-8")
    st_be, _, resp_be_b = await asgi_call(
        "POST",
        "/api/v1/auth/register",
        {"content-type": "application/json"},
        bad_email_body,
    )
    assert st_be == 422
    be_data = json.loads(resp_be_b.decode("utf-8"))
    assert be_data.get("code") == "VALIDATION_ERROR"

    # 5. Validation failure: empty full_name
    empty_name_body = json.dumps(
        {
            "email": "empty@graeae.eye",
            "password": "valid-password-123",
            "full_name": "   ",
        }
    ).encode("utf-8")
    st_en, _, resp_en_b = await asgi_call(
        "POST",
        "/api/v1/auth/register",
        {"content-type": "application/json"},
        empty_name_body,
    )
    assert st_en == 422
    en_data = json.loads(resp_en_b.decode("utf-8"))
    assert en_data.get("code") == "VALIDATION_ERROR"


# =====================================================================
# TEST B: REAL TOKEN AUTHENTICATION & LOGIN OVER DAL
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_real_token_authentication():
    """
    Test B: Validates token authentication via POST /api/v1/auth/token:
    - 200 OK with UserResponse and signed JWT cookie
    - No token in response body
    - Wrong password -> 401 INVALID_CREDENTIALS
    - Unknown email -> 401 INVALID_CREDENTIALS (indistinguishable)
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    # Seed test user in MockDatabase
    test_email = "senior.analyst@graeae.eye"
    test_pw = "correct-horse-battery-staple"
    user_id = uuid4()
    await mock_db.add_record_to_users(
        user_id=user_id,
        email=test_email,
        password_hash=hash_password(test_pw),
        full_name="Senior Analyst Hamilton",
        role="ANALYST",
        is_active=True,
    )

    # 1. Matching credentials -> 200 OK + JWT Cookie
    login_body = json.dumps({"email": test_email, "password": test_pw}).encode("utf-8")
    st, hdrs, b = await asgi_call(
        "POST",
        "/api/v1/auth/token",
        {"content-type": "application/json"},
        login_body,
    )
    assert st == 200, f"Expected 200, got {st}: {b.decode('utf-8')}"
    resp_data = json.loads(b.decode("utf-8"))
    assert resp_data["email"] == test_email
    assert resp_data["user_id"] == str(user_id)
    assert resp_data["role"] == "ANALYST"
    assert "token" not in resp_data
    assert "session_token" not in resp_data
    assert "password_hash" not in resp_data

    # Verify JWT claims in Set-Cookie
    raw_cookie_hdr = get_set_cookie_header(hdrs, "session_token")
    assert raw_cookie_hdr is not None
    assert "HttpOnly" in raw_cookie_hdr
    token_str = extract_cookie(hdrs, "session_token")
    claims = decode_session_token(token_str)
    assert claims["sub"] == str(user_id)
    assert claims["email"] == test_email
    assert claims["role"] == "ANALYST"
    assert claims["iss"] == "graeae-eye"
    assert claims["exp"] > claims["iat"]

    # 2. Wrong password -> 401 INVALID_CREDENTIALS
    wrong_pw_body = json.dumps({"email": test_email, "password": "wrong-password-here"}).encode("utf-8")
    st_wp, _, b_wp = await asgi_call(
        "POST",
        "/api/v1/auth/token",
        {"content-type": "application/json"},
        wrong_pw_body,
    )
    assert st_wp == 401
    wp_data = json.loads(b_wp.decode("utf-8"))
    assert wp_data.get("code") == "INVALID_CREDENTIALS"

    # 3. Nonexistent email -> 401 INVALID_CREDENTIALS (indistinguishable error code/message)
    unknown_email_body = json.dumps({"email": "ghost@graeae.eye", "password": "any-password"}).encode("utf-8")
    st_ue, _, b_ue = await asgi_call(
        "POST",
        "/api/v1/auth/token",
        {"content-type": "application/json"},
        unknown_email_body,
    )
    assert st_ue == 401
    ue_data = json.loads(b_ue.decode("utf-8"))
    assert ue_data.get("code") == "INVALID_CREDENTIALS"
    assert ue_data.get("detail") == wp_data.get("detail")


# =====================================================================
# TEST C: SESSION VALIDATION & PROTECTED ROUTE ACCESS
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_session_validation_and_access():
    """
    Test C: Validates session validation via get_current_user:
    - Public /health accessible without cookie
    - Protected /analysis/stream/<uuid> accessible with valid cookie (reaches 404 RUN_NOT_FOUND)
    - Protected endpoint without cookie -> 401 UNAUTHORIZED
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    # Seed user and create valid JWT
    user_id = uuid4()
    await mock_db.add_record_to_users(
        user_id=user_id,
        email="session.test@graeae.eye",
        password_hash=hash_password("pw-test-12345"),
        full_name="Session Tester",
        role="ANALYST",
        is_active=True,
    )
    jwt_token = create_session_token({"sub": str(user_id), "email": "session.test@graeae.eye", "role": "ANALYST"})
    valid_cookie_hdr = f"session_token={jwt_token}"

    # 1. Public /api/v1/health -> 200 without cookie
    st_health, _, _ = await asgi_call("GET", "/api/v1/health")
    assert st_health == 200

    # 2. Protected /stream/<uuid> without cookie -> 401 UNAUTHORIZED
    target_uuid = uuid4()
    st_no_auth, _, b_no_auth = await asgi_call("GET", f"/api/v1/analysis/stream/{target_uuid}")
    assert st_no_auth == 401
    assert json.loads(b_no_auth.decode("utf-8")).get("code") == "UNAUTHORIZED"

    # 3. Protected /stream/<uuid> with valid cookie -> reaches handler (404 RUN_NOT_FOUND, not 401)
    st_auth, _, b_auth = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{target_uuid}",
        {"cookie": valid_cookie_hdr},
    )
    assert st_auth == 404
    assert json.loads(b_auth.decode("utf-8")).get("code") == "RUN_NOT_FOUND"


# =====================================================================
# TEST D: MOCK FALLBACK REGRESSION (USE_MOCK_ENGINE=true)
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_mock_fallback():
    """
    Test D: Ensures USE_MOCK_ENGINE=true preserves existing mock provider behavior.
    """
    settings.use_mock_engine = True

    # 1. Token authentication with mock fixture credentials
    mock_creds = json.dumps(
        {
            "email": "analyst@graeae.eye",
            "password": "correct-horse-battery-staple",
        }
    ).encode("utf-8")
    st, hdrs, b = await asgi_call(
        "POST",
        "/api/v1/auth/token",
        {"content-type": "application/json"},
        mock_creds,
    )
    assert st == 200
    token_cookie = extract_cookie(hdrs, "session_token")
    assert token_cookie == "mock-session-token-phase1-secret"

    # 2. Protected endpoint accepts mock token
    st_mock_s, _, b_mock_s = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{uuid4()}",
        {"cookie": f"session_token={token_cookie}"},
    )
    assert st_mock_s == 404
    assert "RUN_NOT_FOUND" in b_mock_s.decode("utf-8")


# =====================================================================
# TEST E: TOKEN EXPIRY & SIGNATURE TAMPERING
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_token_expiry_and_tampering():
    """
    Test E: Validates rejection of expired or forged tokens on protected endpoints.
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    user_id = uuid4()
    await mock_db.add_record_to_users(
        user_id=user_id,
        email="tamper.test@graeae.eye",
        password_hash=hash_password("pw-test-12345"),
        full_name="Tamper Tester",
        role="ANALYST",
        is_active=True,
    )

    # 1. Expired JWT (-3600 seconds)
    expired_token = create_session_token(
        {"sub": str(user_id), "email": "tamper.test@graeae.eye", "role": "ANALYST"},
        expires_delta_seconds=-3600,
    )
    st_exp, _, b_exp = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{uuid4()}",
        {"cookie": f"session_token={expired_token}"},
    )
    assert st_exp == 401
    assert json.loads(b_exp.decode("utf-8")).get("code") == "UNAUTHORIZED"

    # 2. Forged JWT signed with wrong secret key
    forged_token = create_session_token(
        {"sub": str(user_id), "email": "tamper.test@graeae.eye", "role": "ANALYST"},
        secret_key="completely-wrong-forged-secret-key-32b",
    )
    st_forged, _, b_forged = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{uuid4()}",
        {"cookie": f"session_token={forged_token}"},
    )
    assert st_forged == 401
    assert json.loads(b_forged.decode("utf-8")).get("code") == "UNAUTHORIZED"

    # 3. Garbage token string
    st_garb, _, b_garb = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{uuid4()}",
        {"cookie": "session_token=not-a-valid-jwt-structure"},
    )
    assert st_garb == 401
    assert json.loads(b_garb.decode("utf-8")).get("code") == "UNAUTHORIZED"


# =====================================================================
# TEST F: SECURITY AUDIT (NO PLAINTEXT PASSWORDS IN LOGS OR RESPONSES)
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_security_audit(caplog):
    """
    Test F: Verifies plaintext passwords never appear in application logs or response bodies.
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    secret_test_password = "super-secret-unique-password-999!"
    unique_email = "audit.user@graeae.eye"

    with caplog.at_level(logging.DEBUG):
        # Register
        reg_body = json.dumps(
            {
                "email": unique_email,
                "password": secret_test_password,
                "full_name": "Audit User",
            }
        ).encode("utf-8")
        st_reg, _, b_reg = await asgi_call(
            "POST",
            "/api/v1/auth/register",
            {"content-type": "application/json"},
            reg_body,
        )
        assert st_reg == 201
        assert "password_hash" not in b_reg.decode("utf-8")

        # Login
        login_body = json.dumps(
            {
                "email": unique_email,
                "password": secret_test_password,
            }
        ).encode("utf-8")
        st_log, _, b_log = await asgi_call(
            "POST",
            "/api/v1/auth/token",
            {"content-type": "application/json"},
            login_body,
        )
        assert st_log == 200
        assert "password_hash" not in b_log.decode("utf-8")

    # Assert plaintext password NEVER appears in any captured log message
    for record in caplog.records:
        assert secret_test_password not in record.message


# =====================================================================
# TARGETED FIX-UP: REMOVE MOCK-TOKEN BACKDOOR FROM REAL-MODE AUTH PATH
# =====================================================================


@pytest.mark.asyncio
async def test_gate4_real_mode_rejects_mock_token():
    """
    Fix-up Test 1: Real mode (USE_MOCK_ENGINE=false, MockDatabase attached) +
    cookie 'mock-session-token-phase1-secret' on GET /api/v1/analysis/stream/<random_uuid>
    MUST return 401 UNAUTHORIZED (P10 envelope).
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    random_id = uuid4()
    st, _, b = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{random_id}",
        {"cookie": "session_token=mock-session-token-phase1-secret"},
    )
    assert st == 401, f"Expected 401, got {st}: {b.decode('utf-8')}"
    resp = json.loads(b.decode("utf-8"))
    assert resp.get("code") == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_gate4_real_mode_rejects_garbage_token():
    """
    Fix-up Test 2: Real mode + cookie 'any-random-garbage-string' -> 401 UNAUTHORIZED.
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    random_id = uuid4()
    st, _, b = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{random_id}",
        {"cookie": "session_token=any-random-garbage-string"},
    )
    assert st == 401, f"Expected 401, got {st}: {b.decode('utf-8')}"
    resp = json.loads(b.decode("utf-8"))
    assert resp.get("code") == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_gate4_real_mode_accepts_valid_jwt_flow():
    """
    Fix-up Test 3: Real mode + valid JWT from register/token flow -> not 401 (regression check).
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    # Register user
    reg_body = json.dumps(
        {
            "email": "fixup.jwt@graeae.eye",
            "password": "valid-password-2026",
            "full_name": "Fixup JWT User",
        }
    ).encode("utf-8")
    st_reg, hdrs_reg, _ = await asgi_call(
        "POST",
        "/api/v1/auth/register",
        {"content-type": "application/json"},
        reg_body,
    )
    assert st_reg == 201
    jwt_val = extract_cookie(hdrs_reg, "session_token")
    assert jwt_val is not None

    random_id = uuid4()
    st_stream, _, b_stream = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{random_id}",
        {"cookie": f"session_token={jwt_val}"},
    )
    assert st_stream != 401, f"Expected non-401, got {st_stream}: {b_stream.decode('utf-8')}"
    assert st_stream == 404
    assert json.loads(b_stream.decode("utf-8")).get("code") == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_gate4_mock_mode_preserves_mock_cookie():
    """
    Fix-up Test 4: Mock mode (USE_MOCK_ENGINE=true) + mock cookie -> 200-class behavior unchanged (regression).
    """
    settings.use_mock_engine = True

    mock_creds = json.dumps(
        {
            "email": "analyst@graeae.eye",
            "password": "correct-horse-battery-staple",
        }
    ).encode("utf-8")
    st, hdrs, b = await asgi_call(
        "POST",
        "/api/v1/auth/token",
        {"content-type": "application/json"},
        mock_creds,
    )
    assert st == 200
    token_cookie = extract_cookie(hdrs, "session_token")
    assert token_cookie == "mock-session-token-phase1-secret"

    random_id = uuid4()
    st_stream, _, b_stream = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{random_id}",
        {"cookie": f"session_token={token_cookie}"},
    )
    assert st_stream == 404
    assert "RUN_NOT_FOUND" in b_stream.decode("utf-8")
