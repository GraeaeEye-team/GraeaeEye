"""
Tests for foreign key parent resolution, start_analysis idempotency,
and currency / financial precision contracts.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
import sys
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from fintech_app.auth.security import create_session_token, hash_password
from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ingestion.pipeline import IngestionPipeline
from fintech_app.ingestion.schemas import NormalizedTransactionSchema
from fintech_app.main import app
from fintech_app.shared.utils import format_currency


async def create_test_auth_cookie(db: Any) -> str:
    """Seeds a test user into the database and returns a signed session_token cookie string."""
    user_id = uuid4()
    await db.add_record_to_users(
        user_id=user_id,
        email="analyst.fk@graeae.eye",
        password_hash=hash_password("password-fk-test-2026"),
        full_name="FK Test Analyst",
        role="ANALYST",
        is_active=True,
    )
    token = create_session_token({"sub": str(user_id), "email": "analyst.fk@graeae.eye", "role": "ANALYST"})
    return f"session_token={token}"


@pytest.mark.asyncio
async def test_analysis_start_idempotency_same_tax_id():
    """
    Submitting multiple analysis requests for the same tax_id must reuse the existing
    business_id and never fail with duplicate key or generate phantom IDs.
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = False

    try:
        auth_cookie = await create_test_auth_cookie(mock_db)
        client = TestClient(app)
        token_val = auth_cookie.split("session_token=")[1]
        client.cookies.set("session_token", token_val)

        csv_content = b"Data,Suma,Detalii,CUI\n2025-01-10,1000.00,Test Payment,1001\n"

        # First request
        resp1 = client.post(
            "/api/v1/analysis/start",
            data={
                "company_name": "Idempotent Enterprise SRL",
                "tax_id": "1009999888877",
                "sector_code": "6201",
                "active_submodules": '["OS","ICR"]',
            },
            files=[("files", ("tx.csv", csv_content, "text/csv"))],
        )
        assert resp1.status_code == 202
        run_id_1 = UUID(resp1.json()["run_id"])

        # Second request with identical tax_id
        resp2 = client.post(
            "/api/v1/analysis/start",
            data={
                "company_name": "Idempotent Enterprise SRL",
                "tax_id": "1009999888877",
                "sector_code": "6201",
                "active_submodules": '["OS","ICR"]',
            },
            files=[("files", ("tx2.csv", csv_content, "text/csv"))],
        )
        assert resp2.status_code == 202
        run_id_2 = UUID(resp2.json()["run_id"])

        assert run_id_1 != run_id_2

        # Verify both analysis_runs point to the EXACT SAME business_id
        row1 = (await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id_1)).data
        row2 = (await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id_2)).data

        assert row1 is not None and row2 is not None
        assert row1["business_id"] == row2["business_id"]

        # Verify only 1 business record was created
        matching_biz = [b for b in mock_db._storage["businesses"] if b["tax_id"] == "1009999888877"]
        assert len(matching_biz) == 1
    finally:
        settings.use_mock_engine = orig_mock


@pytest.mark.asyncio
async def test_ingestion_pipeline_ensures_bank_account_and_counterparty_records():
    """
    IngestionPipeline must guarantee that parent bank_accounts and counterparties records
    exist in the database so foreign keys in transactions are strictly satisfied.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    biz_id = uuid4()
    acc_id = uuid4()

    csv_data = (
        "Data,Suma,Detalii,CUI\n"
        "2025-01-10,5000.00,Incasare marfa,100100100\n"
        "2025-01-11,-2000.00,Plata furnizor materiale,200200200\n"
    ).encode("utf-8")

    result = await pipeline.run(
        metadata={
            "business_id": biz_id,
            "account_id": acc_id,
            "company_name": "Pipeline FK Verification SRL",
            "tax_id": "1008888777766",
        },
        files=[("statement.csv", csv_data)],
    )

    assert result.success is True
    assert result.records_ingested == 2

    # 1. Assert business record exists
    biz_rows = [b for b in mock_db._storage["businesses"] if b["business_id"] == biz_id]
    assert len(biz_rows) == 1

    # 2. Assert bank_accounts record exists for (business_id, account_id)
    acc_rows = [
        a for a in mock_db._storage["bank_accounts"] if a["account_id"] == acc_id and a["business_id"] == biz_id
    ]
    assert len(acc_rows) == 1
    assert acc_rows[0]["currency"] == "MDL"

    # 3. Assert counterparties records exist for the transactions
    cp_rows = [c for c in mock_db._storage["counterparties"] if c["business_id"] == biz_id]
    assert len(cp_rows) >= 1

    # 4. Assert all transactions reference existing bank account and counterparties
    tx_rows = mock_db._storage["transactions"]
    assert len(tx_rows) == 2
    for tx in tx_rows:
        assert tx["account_id"] == acc_id
        assert tx["business_id"] == biz_id
        if tx["counterparty_id"] is not None:
            matching_cp = [c for c in cp_rows if c["counterparty_id"] == tx["counterparty_id"]]
            assert len(matching_cp) == 1


def test_format_currency_mdl_and_decimal():
    """format_currency must handle Decimal and float, defaulting to MDL currency."""
    formatted_dec = format_currency(Decimal("1250000.50"))
    assert formatted_dec == "1,250,000.50 MDL"

    formatted_float = format_currency(3500.0)
    assert formatted_float == "3,500.00 MDL"

    formatted_custom = format_currency(Decimal("500.25"), currency="EUR")
    assert formatted_custom == "500.25 EUR"


def test_normalized_transaction_schema_decimal_amount():
    """NormalizedTransactionSchema must strictly enforce Decimal amount."""
    item = NormalizedTransactionSchema(
        transaction_date=date(2025, 1, 1),
        amount=Decimal("150.75"),
        counterparty_inn="123456",
        description="Office Supplies",
    )
    assert isinstance(item.amount, Decimal)
    assert item.amount == Decimal("150.75")


def test_multilingual_invoice_and_credit_parsing():
    """
    InvoiceParser and CreditObligationParser must handle Russian (Cyrillic)
    and Romanian (diacritics) column headers and localized status/type values.
    """
    from fintech_app.ingestion.parser import CreditObligationParser, InvoiceParser

    # 1. Russian invoice CSV
    ru_invoice_csv = (
        "номер_счета;дата_выставления;дата_оплаты;сумма;тип;статус;инн_контрагента\n"
        "СЧ-2025-01;2025-02-01;2025-03-01;45 000,50;ДОХОД;ОПЛАЧЕН;100200300\n"
        "СЧ-2025-02;2025-02-15;2025-03-15;12 300,00;РАСХОД;ПРОСРОЧЕН;200300400\n"
    ).encode("utf-8")

    invoices = InvoiceParser().parse_csv(ru_invoice_csv)
    assert len(invoices) == 2
    assert invoices[0].counterparty_name == "100200300"
    assert invoices[0].gross_amount == Decimal("45000.50")
    assert invoices[0].invoice_type == "RECEIVABLE"
    assert invoices[0].status == "SETTLED"
    assert invoices[1].invoice_type == "PAYABLE"
    assert invoices[1].status == "OVERDUE"

    # 2. Romanian invoice CSV with diacritics
    ro_invoice_csv = (
        "număr_factură,dată_emitere,dată_scadență,sumă,tip,status,cui_partener\n"
        "FAC-101,2025-01-10,2025-02-10,7500.25,IESIRE,ACHITAT,100555\n"
    ).encode("utf-8")
    ro_invoices = InvoiceParser().parse_csv(ro_invoice_csv)
    assert len(ro_invoices) == 1
    assert ro_invoices[0].counterparty_name == "100555"
    assert ro_invoices[0].gross_amount == Decimal("7500.25")
    assert ro_invoices[0].status == "SETTLED"

    # 3. Russian credit obligation CSV
    ru_credit_csv = (
        "номер_договора;кредитор;начальная_сумма;остаток_задолженности;ставка;тип_кредита;статус;просрочено_дней\n"
        "КР-999;МАИБ Банк;1 000 000,00;450 000,00;11,5;КРЕДИТ;АКТИВЕН;0\n"
    ).encode("utf-8")

    obligations = CreditObligationParser().parse_csv(ru_credit_csv)
    assert len(obligations) == 1
    assert obligations[0].lender_name == "МАИБ Банк"
    assert obligations[0].principal_amount == Decimal("1000000.00")
    assert obligations[0].outstanding_balance == Decimal("450000.00")
    assert obligations[0].facility_type == "TERM_LOAN"


@pytest.mark.asyncio
async def test_start_analysis_with_field_aliases_and_no_files():
    """
    POST /api/v1/analysis/start must accept input_company_name, input_tax_id,
    input_industry_code aliases, and succeed even when files or active_submodules are omitted.
    """
    mock_db = MockDatabase.get_instance()
    mock_db.reset()
    await mock_db.open()
    app.state.db = mock_db
    orig_mock = settings.use_mock_engine
    settings.use_mock_engine = False

    try:
        auth_cookie = await create_test_auth_cookie(mock_db)
        client = TestClient(app)
        token_val = auth_cookie.split("session_token=")[1]
        client.cookies.set("session_token", token_val)

        # Send with alias fields, NO files, NO active_submodules
        resp = client.post(
            "/api/v1/analysis/start",
            data={
                "input_company_name": "Alias Enterprise SRL",
                "input_tax_id": "1005556667778",
                "input_industry_code": "4711",
            },
        )
        assert resp.status_code == 202
        run_data = resp.json()
        assert "run_id" in run_data
        run_id = UUID(run_data["run_id"])

        # Check that analysis_run was created with canonical submodules
        run_row = (await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)).data
        assert run_row is not None
        assert run_row["input_company_name"] == "Alias Enterprise SRL"
        assert run_row["input_tax_id"] == "1005556667778"
        assert len(run_row["active_submodules"]) == 9
    finally:
        settings.use_mock_engine = orig_mock


def test_underwriting_pipeline_selective_submodules():
    """
    When active_submodules is specified, omitted submodules must be marked SKIPPED
    with DATA_ABSENT status, and their feature vector indices must be None.
    """
    from fintech_app.db.models import BusinessRecord, CompanyDataSnapshot
    from fintech_app.ml.base import EvaluationStatus
    from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline

    biz_id = uuid4()
    biz = BusinessRecord(
        business_id=biz_id,
        tax_id="1001112223334",
        legal_name="Selective Test SRL",
        industry_code="6201",
        registration_date=date.today(),
    )
    snapshot = CompanyDataSnapshot(
        business=biz,
        business_id=biz_id,
        shareholders=[],
        web_reputation=None,
        macro_sector_metrics=None,
        counterparties=[],
        invoices=[],
        bank_accounts=[],
        transactions=[],
        credit_obligations=[],
    )

    pipeline = UnderwritingAnalyticalPipeline()
    result = pipeline.run_analysis(snapshot, active_submodules=["OS", "ICR"])

    assert result.submodule_results["OS"].verdict != "SKIPPED"
    assert result.submodule_results["ICR"].verdict != "SKIPPED"

    # WPR, MSR, CD, SD, CFS, RQ, ICDL must be SKIPPED
    for skipped_code in ["WPR", "MSR", "CD", "SD", "CFS", "RQ", "ICDL"]:
        res = result.submodule_results[skipped_code]
        assert res.status == EvaluationStatus.DATA_ABSENT
        assert res.verdict == "SKIPPED"
        for val in res.indices.values():
            assert val is None


def test_credit_scoring_engine_probability_of_default_boundaries():
    """
    CreditScoringEngine.calculate_probability_of_default must return values
    strictly clamped in [0.001, 0.999] without OverflowError.
    """
    from fintech_app.ml.scoring import CreditScoringEngine

    # Neutral score (50.0) -> exactly 0.5000
    pd_50 = CreditScoringEngine.calculate_probability_of_default(50.0)
    assert pd_50 == 0.5000

    # Extremely low score (default guaranteed)
    pd_extreme_low = CreditScoringEngine.calculate_probability_of_default(-10000.0)
    assert pd_extreme_low == 0.999

    # Extremely high score (prime borrower)
    pd_extreme_high = CreditScoringEngine.calculate_probability_of_default(10000.0)
    assert pd_extreme_high == 0.001

    # Standard scores
    pd_0 = CreditScoringEngine.calculate_probability_of_default(0.0)
    assert 0.95 <= pd_0 <= 0.999

    pd_100 = CreditScoringEngine.calculate_probability_of_default(100.0)
    assert 0.001 <= pd_100 <= 0.05


@pytest.mark.asyncio
async def test_ingestion_pipeline_macro_sector_risk_score_range():
    """
    IngestionPipeline must clamp macro_sector_metrics risk_outlook_score
    to [1, 10] to comply with the PostgreSQL CHECK constraint.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    biz_id = uuid4()
    await pipeline.run(
        metadata={
            "business_id": biz_id,
            "company_name": "Macro Constraint Test SRL",
            "tax_id": "1009990001112",
            "sector_code": "6201",
        },
        files=[],
    )

    macro_rows = mock_db._storage["macro_sector_metrics"]
    assert len(macro_rows) >= 1
    for m in macro_rows:
        score = m["risk_outlook_score"]
        assert 1 <= score <= 10, f"Score {score} violates CHECK (risk_outlook_score BETWEEN 1 AND 10)"
        assert m["sector_default_rate"] == Decimal("2.50")
        assert m["sector_growth_rate_yoy"] == Decimal("3.50")
