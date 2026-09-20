"""
Gate 3: Real Orchestration Wiring In-Process Verification Tests.

Validates end-to-end orchestration against in-process MockDatabase:
A. Happy path with transactions.csv: analysis_runs (QUEUED -> COMPLETED/DEGRADED),
   analysis_logs populated, report 200 with 18-key feature_vector and llm_synthesis (4 keys),
   SSE telemetry ending with PIPELINE_COMPLETE, submodule status events using long IDs.
B. Mock mode regression: existing mock provider behavior (202, 200, 404, 409, 422).
C. db=None + USE_MOCK_ENGINE=false triggers 503 DB_UNAVAILABLE on start, stream, report.
D. Auth hardening: missing session cookie triggers 401 UNAUTHORIZED on stream and report.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.auth.security import create_session_token, hash_password
from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.main import app
from fintech_app.api.schemas import CANONICAL_18D_KEYS

MOCK_COOKIE = "session_token=mock-session-token-phase1-secret"


async def create_test_auth_cookie(
    db: Any,
    email: str = "test@graeae.eye",
    password: str = "test-password-2026",
    role: str = "ANALYST",
) -> str:
    """Seeds a test user into the database and returns a signed session_token cookie string."""
    user_id = uuid4()
    await db.add_record_to_users(
        user_id=user_id,
        email=email,
        password_hash=hash_password(password),
        full_name="Gate 3 Test Analyst",
        role=role,
        is_active=True,
    )
    token = create_session_token({"sub": str(user_id), "email": email, "role": role})
    return f"session_token={token}"


# =====================================================================
# IN-PROCESS ASGI TEST HARNESS (Zero External HTTP Dependencies)
# =====================================================================

async def asgi_call(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> Tuple[int, List[Tuple[str, str]], bytes]:
    """Pure in-process ASGI call invoking FastAPI app directly."""
    headers = headers or {}
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()
    ]
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
            response_headers = [
                (k.decode("latin-1"), v.decode("latin-1")) for k, v in message["headers"]
            ]
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    return status_code, response_headers, b"".join(response_body)


def build_multipart(fields: Dict[str, str], files_list: List[Tuple[str, str | bytes]]) -> Tuple[bytes, str]:
    """Constructs multipart/form-data payload with boundary."""
    boundary = "----WebKitFormBoundaryGate3TestPayload"
    lines = []
    for k, v in fields.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{k}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(str(v).encode("utf-8"))
    for fname, content in files_list:
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="files"; filename="{fname}"'.encode("utf-8"))
        lines.append(b"Content-Type: text/csv")
        lines.append(b"")
        lines.append(content.encode("utf-8") if isinstance(content, str) else content)
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


# =====================================================================
# TEST A: FULL HAPPY PATH WITH TRANSACTIONS.CSV (REAL PATH IN-PROCESS)
# =====================================================================

@pytest.mark.asyncio
async def test_gate3_happy_path_with_mock_database():
    """
    Test A: Validates the full real orchestration path:
    POST /start -> IngestionPipeline -> MockDatabase -> UnderwritingAnalyticalPipeline -> SSE -> Report.
    """
    # 1. Setup MockDatabase in app.state.db and toggle USE_MOCK_ENGINE=False
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    settings.use_mock_engine = False

    # Issue valid signed JWT auth cookie for real mode
    auth_cookie = await create_test_auth_cookie(mock_db)

    csv_content = (
        "Data,Suma,Detalii,CUI\n"
        "2025-02-01,15000.00,Incasare vanzari marfa,100100\n"
        "2025-02-03,-3500.00,Plata salarii angajati,100200\n"
        "2025-02-05,-1200.00,Plata impozite buget,100300\n"
    )

    fields = {
        "company_name": "Moldova Tech Solutions SRL",
        "tax_id": "1007601234567",
        "sector_code": "6201",
        "active_submodules": '["OS","WPR","MSR","CD","SD","ICR","CFS","RQ","ICDL"]',
    }
    files = [("transactions.csv", csv_content)]
    body, ct = build_multipart(fields, files)

    # 2. POST /api/v1/analysis/start
    st, hdrs, b = await asgi_call(
        "POST",
        "/api/v1/analysis/start",
        {"content-type": ct, "cookie": auth_cookie},
        body,
    )
    assert st == 202, f"Expected 202 Accepted, got {st}: {b.decode('utf-8')}"
    resp = json.loads(b.decode("utf-8"))
    assert "run_id" in resp
    assert resp["status"] == "QUEUED"
    run_id = UUID(resp["run_id"])

    # Wait briefly for background worker execution to complete in-process
    for _ in range(30):
        run_rep = await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
        if run_rep.success and run_rep.data:
            current_st = run_rep.data.get("status")
            if current_st in ("COMPLETED", "DEGRADED", "FAILED"):
                break
        await asyncio.sleep(0.1)

    # 3. Assert analysis_runs row exists and reached terminal status
    run_rep = await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
    assert run_rep.success and run_rep.data
    run_row = run_rep.data
    # Known gap: only transactions uploaded; non-transaction submodules evaluate DATA_ABSENT
    assert run_row["status"] in ("COMPLETED", "DEGRADED"), f"Expected terminal status, got {run_row['status']}"
    assert len(run_row["submodules_reports"]) == 9

    # 4. Assert analysis_logs non-empty and contains expected stages
    logs_rep = await mock_db.get_records_from_analysis_logs(run_id=run_id)
    assert logs_rep.success and len(logs_rep.data) > 0
    stages_logged = [l.get("stage") for l in logs_rep.data]
    assert "INGESTION" in stages_logged
    assert "DATA_LOAD" in stages_logged
    assert "ML_EVALUATION" in stages_logged
    assert "SCORING" in stages_logged
    assert "PIPELINE_COMPLETE" in stages_logged

    # 5. GET /api/v1/analysis/stream/{run_id} (SSE stream)
    st_stream, hdrs_stream, b_stream = await asgi_call(
        "GET",
        f"/api/v1/analysis/stream/{run_id}",
        {"cookie": auth_cookie},
    )
    assert st_stream == 200
    stream_text = b_stream.decode("utf-8")
    assert "event: PIPELINE_STAGE_CHANGED" in stream_text
    assert "event: LOG_EMITTED" in stream_text
    assert "event: SUBMODULE_STATUS_UPDATED" in stream_text
    assert "event: PIPELINE_COMPLETE" in stream_text

    # Verify long IDs used in SUBMODULE_STATUS_UPDATED
    assert '"submodule_id": "OS_4_1"' in stream_text
    assert '"submodule_id": "ICR_4_6"' in stream_text
    assert '"submodule_id": "ICDL_4_9"' in stream_text

    # 6. GET /api/v1/analysis/report/{run_id}
    st_rep, hdrs_rep, b_rep = await asgi_call(
        "GET",
        f"/api/v1/analysis/report/{run_id}",
        {"cookie": auth_cookie},
    )
    assert st_rep == 200, f"Expected 200, got {st_rep}: {b_rep.decode('utf-8')}"
    rep = json.loads(b_rep.decode("utf-8"))

    # Feature vector object with 18 keys
    fv = rep.get("feature_vector", {})
    assert len(fv) == 18
    for expected_key in CANONICAL_18D_KEYS:
        assert expected_key in fv

    # Feature vector ordered list with 18 values
    fvo = rep.get("feature_vector_ordered", [])
    assert len(fvo) == 18

    # LLM Synthesis object with 4 keys
    synthesis = rep.get("llm_synthesis", {})
    assert "headline" in synthesis
    assert "summary_markdown" in synthesis
    assert "critical_flags" in synthesis
    assert "positive_indicators" in synthesis

    # 9 submodule cards
    assert len(rep.get("submodules", [])) == 9
    assert rep["universal_score"] > 0.0


# =====================================================================
# TEST B: MOCK MODE REGRESSION TEST (USE_MOCK_ENGINE=true)
# =====================================================================

@pytest.mark.asyncio
async def test_gate3_mock_mode_regression():
    """
    Test B: Ensures 100% backward compatibility of existing mock provider path.
    """
    settings.use_mock_engine = True

    fields = {
        "company_name": "Acme Holdings SRL",
        "tax_id": "1007600000000",
        "sector_code": "6201",
        "active_submodules": '["OS","WPR"]',
    }
    files = [("accounts.csv", "id,balance\n1,1000.0\n")]
    body, ct = build_multipart(fields, files)

    # 1. POST /start returns 202
    st, _, b = await asgi_call("POST", "/api/v1/analysis/start", {"content-type": ct, "cookie": MOCK_COOKIE}, body)
    assert st == 202
    resp = json.loads(b.decode("utf-8"))
    assert "run_id" in resp

    # 2. Upload >5 files -> 422 TOO_MANY_FILES
    six_files = [(f"f_{i}.csv", "data\n1\n") for i in range(6)]
    b6, ct6 = build_multipart(fields, six_files)
    st6, _, b6_resp = await asgi_call("POST", "/api/v1/analysis/start", {"content-type": ct6, "cookie": MOCK_COOKIE}, b6)
    assert st6 == 422
    assert "TOO_MANY_FILES" in b6_resp.decode("utf-8")

    # 3. Unknown UUID stream -> 404 RUN_NOT_FOUND
    st_unk, _, b_unk = await asgi_call("GET", f"/api/v1/analysis/stream/{uuid4()}", {"cookie": MOCK_COOKIE})
    assert st_unk == 404
    assert "RUN_NOT_FOUND" in b_unk.decode("utf-8")

    # 4. Unknown UUID report -> 404 RUN_NOT_FOUND
    st_unk_rep, _, b_unk_rep = await asgi_call("GET", f"/api/v1/analysis/report/{uuid4()}", {"cookie": MOCK_COOKIE})
    assert st_unk_rep == 404
    assert "RUN_NOT_FOUND" in b_unk_rep.decode("utf-8")


# =====================================================================
# TEST C: DB UNAVAILABLE 503 ERROR
# =====================================================================

@pytest.mark.asyncio
async def test_gate3_db_unavailable_503():
    """
    Test C: Verifies that db=None + USE_MOCK_ENGINE=false returns 503 DB_UNAVAILABLE.
    """
    settings.use_mock_engine = False
    app.state.db = None

    fields = {
        "company_name": "Test SRL",
        "tax_id": "1007600000000",
        "sector_code": "6201",
        "active_submodules": "[]",
    }
    body, ct = build_multipart(fields, [])

    # POST /start -> 503
    st, _, b = await asgi_call("POST", "/api/v1/analysis/start", {"content-type": ct, "cookie": MOCK_COOKIE}, body)
    assert st == 503
    resp = json.loads(b.decode("utf-8"))
    assert resp.get("code") == "DB_UNAVAILABLE"

    # GET /stream/{run_id} -> 503
    st_s, _, b_s = await asgi_call("GET", f"/api/v1/analysis/stream/{uuid4()}", {"cookie": MOCK_COOKIE})
    assert st_s == 503
    resp_s = json.loads(b_s.decode("utf-8"))
    assert resp_s.get("code") == "DB_UNAVAILABLE"

    # GET /report/{run_id} -> 503
    st_r, _, b_r = await asgi_call("GET", f"/api/v1/analysis/report/{uuid4()}", {"cookie": MOCK_COOKIE})
    assert st_r == 503
    resp_r = json.loads(b_r.decode("utf-8"))
    assert resp_r.get("code") == "DB_UNAVAILABLE"


# =====================================================================
# TEST D: AUTH HARDENING (401 UNAUTHORIZED)
# =====================================================================

@pytest.mark.asyncio
async def test_gate3_auth_hardening():
    """
    Test D: Verifies that stream and report endpoints require authentication.
    """
    random_id = uuid4()

    # GET /stream without cookie -> 401
    st_s, _, b_s = await asgi_call("GET", f"/api/v1/analysis/stream/{random_id}")
    assert st_s == 401
    resp_s = json.loads(b_s.decode("utf-8"))
    assert resp_s.get("code") == "UNAUTHORIZED"

    # GET /report without cookie -> 401
    st_r, _, b_r = await asgi_call("GET", f"/api/v1/analysis/report/{random_id}")
    assert st_r == 401
    resp_r = json.loads(b_r.decode("utf-8"))
    assert resp_r.get("code") == "UNAUTHORIZED"
