"""
Test Suite: User Isolation, History Ledger & Access Control.

Verifies:
1. Multi-Tenant Isolation: User B cannot access User A's report or SSE stream (HTTP 403).
2. Admin Override: Administrators can inspect any run regardless of owner.
3. History Ledger Endpoint: GET /api/v1/analysis/history strictly filters by tenant.
4. Query Parameter Token: EventSource SSE stream accepts ?token= parameter for auth.
"""

from __future__ import annotations

import os
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.auth.security import create_session_token
from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_sse_stream_query_param_token_authentication(client):
    """EventSource query param token (?token=...) must authenticate requests."""
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = True

    try:
        user_id = uuid4()
        token = create_session_token({"sub": str(user_id), "email": "user@test.org", "role": "ANALYST"})

        # Start an analysis run for user
        resp = client.post(
            "/api/v1/analysis/start",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "company_name": "Test Company SRL",
                "tax_id": "1002003004001",
                "sector_code": "G46",
            },
            files={"bank_statement_file": ("statement.csv", b"date,amount,direction\n2025-01-01,100,INFLOW\n", "text/csv")},
        )
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        # Stream with valid token in query parameter
        stream_resp = client.get(f"/api/v1/analysis/stream/{run_id}?token={token}")
        assert stream_resp.status_code == 200

        # Stream with NO credentials must fail with 401
        no_auth_resp = client.get(f"/api/v1/analysis/stream/{run_id}")
        assert no_auth_resp.status_code == 401

    finally:
        settings.use_mock_engine = orig_mock


def test_tenant_isolation_and_forbidden_access(client):
    """User B must receive HTTP 403 when requesting User A's report or stream."""
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = True

    try:
        user_a_id = uuid4()
        user_b_id = uuid4()
        token_a = create_session_token({"sub": str(user_a_id), "email": "usera@test.org", "role": "ANALYST"})
        token_b = create_session_token({"sub": str(user_b_id), "email": "userb@test.org", "role": "ANALYST"})

        # User A starts run
        resp_a = client.post(
            "/api/v1/analysis/start",
            headers={"Authorization": f"Bearer {token_a}"},
            data={
                "company_name": "Company Alpha SRL",
                "tax_id": "1001112223334",
                "sector_code": "C10",
            },
            files={"bank_statement_file": ("statement.csv", b"date,amount\n2025-01-01,500\n", "text/csv")},
        )
        assert resp_a.status_code == 202
        run_id_a = resp_a.json()["run_id"]

        # User B attempts to access User A's stream -> 403 Forbidden
        stream_b = client.get(
            f"/api/v1/analysis/stream/{run_id_a}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert stream_b.status_code == 403
        assert stream_b.json()["code"] == "FORBIDDEN"

        # User B attempts to access User A's report -> 403 Forbidden
        report_b = client.get(
            f"/api/v1/analysis/report/{run_id_a}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert report_b.status_code == 403
        assert report_b.json()["code"] == "FORBIDDEN"

    finally:
        settings.use_mock_engine = orig_mock


def test_admin_override_access(client):
    """Admins must be able to view any report or stream across all tenants."""
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = True

    try:
        user_a_id = uuid4()
        admin_id = uuid4()
        token_a = create_session_token({"sub": str(user_a_id), "email": "usera@test.org", "role": "ANALYST"})
        token_admin = create_session_token({"sub": str(admin_id), "email": "admin@test.org", "role": "ADMIN"})

        # User A creates a run
        resp_a = client.post(
            "/api/v1/analysis/start",
            headers={"Authorization": f"Bearer {token_a}"},
            data={
                "company_name": "Company Beta SRL",
                "tax_id": "1005556667778",
                "sector_code": "M70",
            },
            files={"bank_statement_file": ("statement.csv", b"date,amount\n2025-01-01,500\n", "text/csv")},
        )
        assert resp_a.status_code == 202
        run_id_a = resp_a.json()["run_id"]

        # Admin accesses stream -> 200 OK
        admin_stream = client.get(
            f"/api/v1/analysis/stream/{run_id_a}",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert admin_stream.status_code == 200

    finally:
        settings.use_mock_engine = orig_mock


def test_history_ledger_endpoint_isolation(client):
    """GET /api/v1/analysis/history returns only runs belonging to active tenant."""
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = True

    try:
        user_x_id = uuid4()
        user_y_id = uuid4()
        admin_id = uuid4()

        token_x = create_session_token({"sub": str(user_x_id), "email": "userx@test.org", "role": "ANALYST"})
        token_y = create_session_token({"sub": str(user_y_id), "email": "usery@test.org", "role": "ANALYST"})
        token_admin = create_session_token({"sub": str(admin_id), "email": "superadmin@test.org", "role": "ADMIN"})

        # User X starts run
        resp_x = client.post(
            "/api/v1/analysis/start",
            headers={"Authorization": f"Bearer {token_x}"},
            data={
                "company_name": "Company X SRL",
                "tax_id": "1009998887771",
                "sector_code": "A01",
            },
            files={"bank_statement_file": ("statement.csv", b"date,amount\n2025-01-01,100\n", "text/csv")},
        )
        assert resp_x.status_code == 202
        run_id_x = resp_x.json()["run_id"]

        # User Y starts run
        resp_y = client.post(
            "/api/v1/analysis/start",
            headers={"Authorization": f"Bearer {token_y}"},
            data={
                "company_name": "Company Y SRL",
                "tax_id": "1009998887772",
                "sector_code": "B08",
            },
            files={"bank_statement_file": ("statement.csv", b"date,amount\n2025-01-01,200\n", "text/csv")},
        )
        assert resp_y.status_code == 202
        run_id_y = resp_y.json()["run_id"]

        # User X history must contain run_id_x and NOT run_id_y
        history_x = client.get("/api/v1/analysis/history", headers={"Authorization": f"Bearer {token_x}"})
        assert history_x.status_code == 200
        items_x = history_x.json()["items"]
        run_ids_x = [item["run_id"] for item in items_x]
        assert run_id_x in run_ids_x
        assert run_id_y not in run_ids_x

        # User Y history must contain run_id_y and NOT run_id_x
        history_y = client.get("/api/v1/analysis/history", headers={"Authorization": f"Bearer {token_y}"})
        assert history_y.status_code == 200
        items_y = history_y.json()["items"]
        run_ids_y = [item["run_id"] for item in items_y]
        assert run_id_y in run_ids_y
        assert run_id_x not in run_ids_y

        # Admin history must contain both
        history_admin = client.get("/api/v1/analysis/history", headers={"Authorization": f"Bearer {token_admin}"})
        assert history_admin.status_code == 200
        items_admin = history_admin.json()["items"]
        admin_run_ids = [item["run_id"] for item in items_admin]
        assert run_id_x in admin_run_ids
        assert run_id_y in admin_run_ids

    finally:
        settings.use_mock_engine = orig_mock

