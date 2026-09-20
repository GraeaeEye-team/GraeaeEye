"""
Contract tests for API schemas, 18D feature vector, P10 error envelope, and HTTP status codes.
Specification: docs/ui_architecture.md, Web Interface & Orchestration Layer v2.0
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import io
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from fintech_app.api.contract_mapping import map_ml_result_to_analysis_report
from fintech_app.api.schemas import (
    CANONICAL_18D_KEYS,
    ErrorResponse,
    FeatureVector,
)
from fintech_app.auth.security import create_session_token, hash_password
from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.main import app
from fintech_app.ml.pipeline import UnderwritingPipelineResult
from fintech_app.ml.scoring import CreditScoringEngine, CreditScoringResult

MOCK_COOKIE = "session_token=mock-session-token-phase1-secret"


# =====================================================================
# ASGI TEST CALL UTILITY
# =====================================================================


async def asgi_call(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> Tuple[int, Dict[str, str], bytes]:
    """Helper to dispatch ASGI requests directly to app without live TCP sockets."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin1"), v.encode("latin1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    response_status = 200
    response_headers: Dict[str, str] = {}
    response_body = io.BytesIO()

    async def receive() -> Dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Dict[str, Any]) -> None:
        nonlocal response_status, response_headers
        if message["type"] == "http.response.start":
            response_status = message["status"]
            for h_name, h_val in message.get("headers", []):
                response_headers[h_name.decode("latin1")] = h_val.decode("latin1")
        elif message["type"] == "http.response.body":
            response_body.write(message.get("body", b""))

    await app(scope, receive, send)
    return response_status, response_headers, response_body.getvalue()


def build_multipart(fields: Dict[str, str], files: List[Tuple[str, str | bytes]]) -> Tuple[bytes, str]:
    """Builds multipart/form-data payload with boundary."""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(f"--{boundary}\r\n".encode("utf-8"))
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        buf.write(f"{value}\r\n".encode("utf-8"))
    for filename, content in files:
        buf.write(f"--{boundary}\r\n".encode("utf-8"))
        buf.write(f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode("utf-8"))
        buf.write(b"Content-Type: application/octet-stream\r\n\r\n")
        buf.write(content.encode("utf-8") if isinstance(content, str) else content)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode("utf-8"))
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


# =====================================================================
# 1. CANONICAL 18D FEATURE VECTOR ORDER
# =====================================================================


def test_canonical_18d_feature_vector_order():
    """Asserts CANONICAL_18D_KEYS has exactly 18 items in frozen spec sequence."""
    expected_order = [
        "ownership_dispersion_index",
        "governance_independence_index",
        "legal_cleanliness_index",
        "public_reputation_index",
        "sector_vitality_index",
        "client_diversification_index",
        "top_client_exposure_index",
        "supplier_diversification_index",
        "supply_chain_robustness_index",
        "cash_readiness_index",
        "runway_buffer_index",
        "revenue_predictability_index",
        "revenue_trajectory_index",
        "receivables_safety_index",
        "client_payment_discipline_index",
        "debt_repayment_discipline_index",
        "debt_service_coverage_index",
        "solvency_leverage_index",
    ]
    # 1. Length is exactly 18
    assert len(CANONICAL_18D_KEYS) == 18

    # 2. Strict order matches expected specification
    assert CANONICAL_18D_KEYS == expected_order

    # 3. Pydantic FeatureVector fields match sequence
    assert list(FeatureVector.model_fields.keys()) == expected_order

    # 4. Strict 1-to-1 bijection with ML feature names in lowercase
    ml_names_lower = [name.lower() for name in CreditScoringEngine.FEATURE_NAMES]
    assert ml_names_lower == expected_order


# =====================================================================
# 2. STANDARDIZED P10 ERROR ENVELOPE STRUCTURE
# =====================================================================


def test_p10_error_envelope_structure():
    """Asserts all error responses return strictly structured {'detail': str, 'code': str}."""
    # 1. Valid instance instantiation
    valid_err = ErrorResponse(detail="Operation failed due to missing inputs.", code="INVALID_INPUT")
    dump = valid_err.model_dump()
    assert dump == {"detail": "Operation failed due to missing inputs.", "code": "INVALID_INPUT"}
    assert set(dump.keys()) == {"detail", "code"}

    # 2. Extra keys are strictly forbidden
    with pytest.raises(ValidationError):
        ErrorResponse(detail="Failed", code="ERR", unexpected_key="disallowed")

    # 3. Missing fields trigger ValidationError
    with pytest.raises(ValidationError):
        ErrorResponse(code="MISSING_DETAIL")  # type: ignore

    with pytest.raises(ValidationError):
        ErrorResponse(detail="MISSING_CODE")  # type: ignore


# =====================================================================
# 3. STATUS CODES & ERROR CODES MAPPING
# =====================================================================


@pytest.mark.asyncio
async def test_status_codes_mapping():
    """
    Asserts standard status codes and their associated P10 error codes:
    - 401 UNAUTHORIZED
    - 404 RUN_NOT_FOUND
    - 409 RUN_NOT_READY
    - 422 VALIDATION_ERROR
    - 422 TOO_MANY_FILES
    - 503 DB_UNAVAILABLE
    """
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = True

    try:
        # A. 401 UNAUTHORIZED (missing auth cookie)
        st_401, _, b_401 = await asgi_call("GET", f"/api/v1/analysis/stream/{uuid4()}")
        assert st_401 == 401
        data_401 = json.loads(b_401.decode("utf-8"))
        assert data_401.get("code") == "UNAUTHORIZED"

        # B. 404 RUN_NOT_FOUND (unknown analysis run id)
        st_404, _, b_404 = await asgi_call("GET", f"/api/v1/analysis/report/{uuid4()}", {"cookie": MOCK_COOKIE})
        assert st_404 == 404
        data_404 = json.loads(b_404.decode("utf-8"))
        assert data_404.get("code") == "RUN_NOT_FOUND"

        # C. 422 TOO_MANY_FILES (>5 files uploaded to /analysis/start)
        client = TestClient(app)
        mock_token_val = MOCK_COOKIE.split("session_token=")[1]
        client.cookies.set("session_token", mock_token_val)

        six_files = [("files", (f"file_{i}.csv", b"col\nval\n", "text/csv")) for i in range(6)]
        resp_too_many = client.post(
            "/api/v1/analysis/start",
            data={
                "company_name": "Test Co",
                "tax_id": "1234567890123",
                "sector_code": "6201",
                "active_submodules": '["OS","WPR"]',
            },
            files=six_files,
        )
        assert resp_too_many.status_code == 422
        data_422_files = resp_too_many.json()
        assert data_422_files.get("code") == "TOO_MANY_FILES"

        # D. 422 VALIDATION_ERROR (malformed payload for registration)
        bad_json = json.dumps({"email": "not-an-email", "password": "short"}).encode("utf-8")
        st_422_val, _, b_422_val = await asgi_call(
            "POST",
            "/api/v1/auth/register",
            {"content-type": "application/json"},
            bad_json,
        )
        assert st_422_val == 422
        data_422_val = json.loads(b_422_val.decode("utf-8"))
        assert data_422_val.get("code") == "VALIDATION_ERROR"

        # E. 409 RUN_NOT_READY (analysis run is QUEUED or PROCESSING)
        db = MockDatabase()
        await db.open()
        app.state.db = db
        settings.use_mock_engine = False

        user_id = uuid4()
        await db.add_record_to_users(
            user_id=user_id,
            email="contracts@graeae.eye",
            password_hash=hash_password("contract-secret-2026"),
            full_name="Contract Analyst",
            role="ANALYST",
            is_active=True,
        )
        jwt_token = create_session_token({"sub": str(user_id), "email": "contracts@graeae.eye", "role": "ANALYST"})
        auth_cookie = f"session_token={jwt_token}"

        run_id = uuid4()
        await db.add_record_to_analysis_runs(
            user_id=user_id,
            input_company_name="Pending Co",
            input_tax_id="1111111111111",
            input_industry_code="A01",
            files_manifest={},
            active_submodules=[],
            status="PROCESSING",
            run_id=run_id,
        )

        st_409, _, b_409 = await asgi_call(
            "GET",
            f"/api/v1/analysis/report/{run_id}",
            {"cookie": auth_cookie},
        )
        assert st_409 == 409
        data_409 = json.loads(b_409.decode("utf-8"))
        assert data_409.get("code") == "RUN_NOT_READY"

        # F. 503 DB_UNAVAILABLE (db is None when USE_MOCK_ENGINE=false)
        app.state.db = None
        st_503, _, b_503 = await asgi_call(
            "GET",
            f"/api/v1/analysis/report/{uuid4()}",
            {"cookie": MOCK_COOKIE},
        )
        assert st_503 == 503
        data_503 = json.loads(b_503.decode("utf-8"))
        assert data_503.get("code") == "DB_UNAVAILABLE"

    finally:
        settings.use_mock_engine = orig_mock


# =====================================================================
# 4. FEATURE VECTOR BIJECTION WITH ML
# =====================================================================


def test_feature_vector_bijection_with_ml():
    """Asserts map_ml_result_to_analysis_report produces 18 keys matching CANONICAL_18D_KEYS exactly."""
    # Create canonical 18-element vector with arbitrary float values
    test_values = [float(i * 5.0) for i in range(18)]
    biz_id = uuid4()
    run_id = uuid4()
    now_utc = datetime.now(timezone.utc)

    scoring_result = CreditScoringResult(
        investment_attractiveness_score=80.0,
        probability_of_default=0.04,
        verdict_category="PRIME_LOW_RISK",
        recommendation="APPROVED",
        executive_summary="Bijection verification dossier.",
    )

    pipeline_result = UnderwritingPipelineResult(
        business_id=biz_id,
        as_of_date=date.today(),
        feature_vector=test_values,
        submodule_results={},
        compiled_dossier_text="Full dossier text",
        scoring_result=scoring_result,
    )

    # Execute contract mapping
    report = map_ml_result_to_analysis_report(
        pipeline_result=pipeline_result,
        run_id=run_id,
        created_at=now_utc,
        completed_at=now_utc,
    )

    # 1. Feature vector object fields match CANONICAL_18D_KEYS
    fv_dict = report.feature_vector.model_dump()
    assert list(fv_dict.keys()) == CANONICAL_18D_KEYS
    assert len(fv_dict) == 18

    # 2. Ordered list matches exactly
    assert report.feature_vector_ordered == test_values

    # 3. Values correspond 1-to-1 to input indices
    for idx, key in enumerate(CANONICAL_18D_KEYS):
        assert fv_dict[key] == test_values[idx]
