"""
Test Module 4: API Presentation & Gateway Robustness.
Validates:
- Multi-Part Form Upload with Form Aliases (bank_statement_file, invoices_file, credit_obligations_file).
- Dual Authentication Support (JSON payload vs OAuth2 application/x-www-form-urlencoded).
- Presentation Contract Consistency (zero NaN, canonical 18D keys, presentation fields/aliases).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.api.contract_mapping import map_ml_result_to_analysis_report
from fintech_app.api.schemas import (
    AnalysisReportResponse,
)
from fintech_app.auth.security import create_session_token, hash_password
from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.main import app
from fintech_app.ml.base import EvaluationStatus, SubmoduleResult
from fintech_app.ml.pipeline import UnderwritingPipelineResult
from fintech_app.ml.scoring import CreditScoringResult


# =============================================================================
# 4.1. MULTI-PART FORM UPLOAD WITH FORM ALIASES
# =============================================================================


@pytest.mark.asyncio
async def test_multipart_upload_with_file_aliases():
    """
    Test 4.1: POST /api/v1/analysis/start must accept alternative file field names:
    - bank_statement_file / bank_statement
    - invoices_file / invoices
    - credit_obligations_file / credit_obligations
    and successfully queue analysis (202 ACCEPTED).
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = False

    try:
        user_id = uuid4()
        await mock_db.add_record_to_users(
            user_id=user_id,
            email="analyst.api@graeae.eye",
            password_hash=hash_password("Pass123!"),
            full_name="API Analyst",
            role="ANALYST",
            is_active=True,
        )
        token = create_session_token({"sub": str(user_id), "email": "analyst.api@graeae.eye", "role": "ANALYST"})

        client = TestClient(app)
        client.cookies.set("session_token", token)

        statement_bytes = b"Data,Suma,Detalii,CUI\n2025-01-10,5000.00,Client Payment,1001\n"
        invoices_bytes = b"counterparty_name,gross_amount\nClient SRL,7500.00\n"
        obligations_bytes = b"lender_name,principal_amount\nmaib,50000.00\n"

        # Case A: Using *_file aliases
        resp_a = client.post(
            "/api/v1/analysis/start",
            data={
                "company_name": "Alias Enterprise SRL",
                "tax_id": "1009998881234",
                "sector_code": "6201",
            },
            files=[
                ("bank_statement_file", ("statement.csv", statement_bytes, "text/csv")),
                ("invoices_file", ("invoices.csv", invoices_bytes, "text/csv")),
                ("credit_obligations_file", ("obligations.csv", obligations_bytes, "text/csv")),
            ],
        )
        assert resp_a.status_code == 202
        data_a = resp_a.json()
        assert "run_id" in data_a
        assert data_a["status"] == "QUEUED"

        # Case B: Using direct role aliases (bank_statement, invoices, credit_obligations)
        resp_b = client.post(
            "/api/v1/analysis/start",
            data={
                "input_company_name": "Alias Enterprise 2 SRL",
                "input_tax_id": "1009998881235",
                "input_industry_code": "6201",
            },
            files=[
                ("bank_statement", ("tx.csv", statement_bytes, "text/csv")),
                ("invoices", ("inv.csv", invoices_bytes, "text/csv")),
                ("credit_obligations", ("obl.csv", obligations_bytes, "text/csv")),
            ],
        )
        assert resp_b.status_code == 202
        data_b = resp_b.json()
        assert "run_id" in data_b
        assert data_b["status"] == "QUEUED"
    finally:
        settings.use_mock_engine = orig_mock


# =============================================================================
# 4.2. DUAL AUTHENTICATION SUPPORT (JSON VS OAUTH2 FORM)
# =============================================================================


@pytest.mark.asyncio
async def test_dual_authentication_support():
    """
    Test 4.2: POST /api/v1/auth/token must accept both:
    1. application/json: {"email": "...", "password": "..."}
    2. application/x-www-form-urlencoded: username=...&password=... (OAuth2 spec)
    returning access_token, token_type='bearer', and setting session_token cookie.
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = False

    try:
        user_id = uuid4()
        test_email = "dual.auth@graeae.eye"
        test_password = "SecurePassword2026!"

        await mock_db.add_record_to_users(
            user_id=user_id,
            email=test_email,
            password_hash=hash_password(test_password),
            full_name="Dual Auth User",
            role="RISK_OFFICER",
            is_active=True,
        )

        client = TestClient(app)

        # 1. JSON Authentication Path
        resp_json = client.post(
            "/api/v1/auth/token",
            json={"email": test_email, "password": test_password},
        )
        assert resp_json.status_code == 200
        body_json = resp_json.json()
        assert body_json["email"] == test_email
        assert body_json["role"] == "RISK_OFFICER"
        assert "access_token" in body_json
        assert body_json["token_type"] == "bearer"
        assert "session_token" in resp_json.cookies

        # 2. OAuth2 Form URL-encoded Authentication Path
        resp_form = client.post(
            "/api/v1/auth/token",
            data={"username": test_email, "password": test_password},
        )
        assert resp_form.status_code == 200
        body_form = resp_form.json()
        assert body_form["email"] == test_email
        assert "access_token" in body_form
        assert body_form["token_type"] == "bearer"
        assert "session_token" in resp_form.cookies

        # 3. Invalid credentials rejection
        resp_bad = client.post(
            "/api/v1/auth/token",
            data={"username": test_email, "password": "wrong-password"},
        )
        assert resp_bad.status_code == 401
        assert resp_bad.json()["code"] == "INVALID_CREDENTIALS"
    finally:
        settings.use_mock_engine = orig_mock


# =============================================================================
# 4.3. PRESENTATION CONTRACT CONSISTENCY
# =============================================================================


def test_presentation_contract_consistency():
    """
    Test 4.3: Validates that AnalysisReportResponse produces a consistent,
    well-formed JSON contract without NaNs, nulls in numeric fields, and
    provides presentation aliases (score, risk_band, decision, application_id).
    """
    run_id = uuid4()
    biz_id = uuid4()

    # Build synthetic 18D feature vector with clean floats
    ordered_fv = [
        75.0,
        80.0,
        95.0,
        85.0,
        65.0,
        70.0,
        80.0,
        72.0,
        68.0,
        90.0,
        85.0,
        77.0,
        82.0,
        88.0,
        92.0,
        95.0,
        84.0,
        78.0,
    ]
    assert len(ordered_fv) == 18

    # Build submodule results dictionary with canonical index keys
    sub_results = {
        "OS": SubmoduleResult(
            submodule_code="OS",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.08,
            verdict="BALANCED_GOVERNANCE",
            indices={"Ownership_Dispersion_Index": 75.0, "Governance_Independence_Index": 80.0},
            summary="Balanced ownership and governance.",
            diagnostic_report="[OS] SUCCESS",
        ),
        "WPR": SubmoduleResult(
            submodule_code="WPR",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.12,
            verdict="CLEAN_REPUTATION",
            indices={"Legal_Cleanliness_Index": 95.0, "Public_Reputation_Index": 85.0},
            summary="Spotless web reputation.",
            diagnostic_report="[WPR] SUCCESS",
        ),
        "MSR": SubmoduleResult(
            submodule_code="MSR",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.05,
            verdict="EXPANDING_SECTOR",
            indices={"Sector_Vitality_Index": 65.0},
            summary="Growing sector.",
            diagnostic_report="[MSR] SUCCESS",
        ),
        "CD": SubmoduleResult(
            submodule_code="CD",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.10,
            verdict="DIVERSIFIED",
            indices={"Client_Diversification_Index": 70.0, "Top_Client_Exposure_Index": 80.0},
            summary="Good client diversification.",
            diagnostic_report="[CD] SUCCESS",
        ),
        "SD": SubmoduleResult(
            submodule_code="SD",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.08,
            verdict="ROBUST",
            indices={"Supplier_Diversification_Index": 72.0, "Supply_Chain_Robustness_Index": 68.0},
            summary="Robust supplier chain.",
            diagnostic_report="[SD] SUCCESS",
        ),
        "ICR": SubmoduleResult(
            submodule_code="ICR",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.15,
            verdict="LIQUID",
            indices={"Cash_Readiness_Index": 90.0, "Runway_Buffer_Index": 85.0},
            summary="High cash readiness.",
            diagnostic_report="[ICR] SUCCESS",
        ),
        "CFS": SubmoduleResult(
            submodule_code="CFS",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.08,
            verdict="STABLE",
            indices={"Revenue_Predictability_Index": 77.0, "Revenue_Trajectory_Index": 82.0},
            summary="Stable revenue inflows.",
            diagnostic_report="[CFS] SUCCESS",
        ),
        "RQ": SubmoduleResult(
            submodule_code="RQ",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.14,
            verdict="HIGH_QUALITY",
            indices={"Receivables_Safety_Index": 88.0, "Client_Payment_Discipline_Index": 92.0},
            summary="Safe receivables profile.",
            diagnostic_report="[RQ] SUCCESS",
        ),
        "ICDL": SubmoduleResult(
            submodule_code="ICDL",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.16,
            verdict="LOW_LEVERAGE",
            indices={
                "Debt_Repayment_Discipline_Index": 95.0,
                "Debt_Service_Coverage_Index": 84.0,
                "Solvency_Leverage_Index": 78.0,
            },
            summary="Controlled debt profile.",
            diagnostic_report="[ICDL] SUCCESS",
        ),
    }

    scoring_res = CreditScoringResult(
        investment_attractiveness_score=81.50,
        probability_of_default=0.0150,
        verdict_category="PRIME_LOW_RISK",
        recommendation="APPROVED",
        executive_summary="Solid enterprise profile.",
    )

    pipeline_result = UnderwritingPipelineResult(
        business_id=biz_id,
        as_of_date=date.today(),
        feature_vector=ordered_fv,
        submodule_results=sub_results,
        compiled_dossier_text="Executive dossier",
        scoring_result=scoring_res,
    )

    now = datetime.now(timezone.utc)
    report = map_ml_result_to_analysis_report(
        pipeline_result=pipeline_result,
        run_id=run_id,
        company_name="Moldova IT Hub SRL",
        tax_id="1009990008888",
        sector_code="6201",
        created_at=now,
        completed_at=now,
        max_credit_limit_mdl=Decimal("1500000.00"),
    )

    assert isinstance(report, AnalysisReportResponse)

    # 1. Check presentation aliases
    assert report.score == 81.50
    assert report.universal_score == 81.50
    assert report.risk_band == "PRIME_LOW_RISK"
    assert report.verdict_category == "PRIME_LOW_RISK"
    assert report.decision == "APPROVED"
    assert report.recommendation == "APPROVED"
    assert report.application_id == run_id
    assert report.run_id == run_id

    # 2. Serialize to JSON and verify strict contract validity
    serialized_dict = report.model_dump(mode="json")
    serialized_str = json.dumps(serialized_dict)

    # Must NOT contain NaN or invalid floats
    assert "NaN" not in serialized_str
    assert "Infinity" not in serialized_str

    # Must contain root presentation fields
    assert "score" in serialized_dict
    assert "risk_band" in serialized_dict
    assert "decision" in serialized_dict
    assert "application_id" in serialized_dict
    assert "max_credit_limit_mdl" in serialized_dict

    # max_credit_limit_mdl strictly numeric / decimal
    assert Decimal(str(serialized_dict["max_credit_limit_mdl"])) == Decimal("1500000.00")
