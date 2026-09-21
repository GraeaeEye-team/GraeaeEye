"""
Integration test suite for atomic multi-document ingestion pipeline (Test Module 2).
Validates multi-document bundles (Bank Statement + Invoices + Credit Obligations),
automatic foreign-key parent record resolution, transactional rollback integrity,
and multi-submission idempotency against DAL MockDatabase.
"""

from __future__ import annotations

from decimal import Decimal
import io
import os
import sys
from uuid import uuid4

import openpyxl
import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.core.exceptions import ParsingError
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ingestion.pipeline import IngestionPipeline


def create_xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    """Helper to create XLSX bytes in memory for tests."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_atomic_multidoc_bundle_ingestion():
    """
    Test 2.1: Ingests a complete multi-document bundle in a single run:
    - Bank statement CSV (with inflow & outflow transactions)
    - Invoices CSV (payable & receivable invoices)
    - Credit obligations XLSX (credit line & term loan)
    Verifies that all 3 datasets + external intelligence are persisted into the DAL.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    biz_id = uuid4()
    acc_id = uuid4()

    statement_csv = (
        "Data,Suma,Detalii,CUI\n"
        "2025-01-10,15000.00,Incasare vanzari marfa,100100100\n"
        "2025-01-11,-5000.00,Plata chirie birou,200200200\n"
    ).encode("utf-8")

    invoices_csv = (
        "numar_factura,data_emiterii,termen_plata,suma_totala,directie,status,cui_furnizor\n"
        "FAC-101,2025-01-05,2025-02-05,25000.00,IESIRE,ACHITAT,100100100\n"
        "FAC-102,2025-01-06,2025-02-06,8500.00,INTRARE,EXPIRAT,300300300\n"
    ).encode("utf-8")

    credit_xlsx = create_xlsx_bytes(
        headers=["creditor", "tip_credit", "suma_credit", "sold", "rata_lunara", "past_due_30d", "past_due_90d"],
        rows=[
            ["maib", "LINIE_DE_CREDIT", 500000.0, 320000.0, 15000.0, 0, 0],
            ["Victoriabank", "TERM_LOAN", 200000.0, 100000.0, 8000.0, 1, 0],
        ],
    )

    metadata = {
        "business_id": biz_id,
        "account_id": acc_id,
        "company_name": "Agro Alianța SRL",
        "tax_id": "1009998887771",
        "sector_code": "0111",
    }

    files = [
        ("extras_cont.csv", statement_csv),
        ("facturi_fiscale.csv", invoices_csv),
        ("credite_bancare.xlsx", credit_xlsx),
    ]

    result = await pipeline.run(metadata=metadata, files=files)
    assert result.success is True
    assert result.records_ingested >= 6  # 2 tx + 2 inv + 2 obl

    # 1. Verify transactions persisted with correct Decimal amounts
    tx_rows = mock_db._storage["transactions"]
    assert len(tx_rows) == 2
    assert all(tx["business_id"] == biz_id for tx in tx_rows)
    assert all(isinstance(tx["amount"], Decimal) for tx in tx_rows)

    # 2. Verify invoices persisted with foreign keys linked
    inv_rows = mock_db._storage["invoices"]
    assert len(inv_rows) == 2
    assert all(inv["business_id"] == biz_id for inv in inv_rows)
    assert all(isinstance(inv["gross_amount"], Decimal) for inv in inv_rows)
    assert {inv["status"] for inv in inv_rows} == {"SETTLED", "OVERDUE"}

    # 3. Verify credit obligations persisted
    obl_rows = mock_db._storage["credit_obligations"]
    assert len(obl_rows) == 2
    assert all(obl["business_id"] == biz_id for obl in obl_rows)
    assert {obl["facility_type"] for obl in obl_rows} == {"CREDIT_LINE", "TERM_LOAN"}

    # 4. Verify external intelligence records created
    rep_rows = mock_db._storage["web_reputation"]
    assert len(rep_rows) >= 1
    assert rep_rows[0]["business_id"] == biz_id

    macro_rows = mock_db._storage["macro_sector_metrics"]
    assert len(macro_rows) >= 1


@pytest.mark.asyncio
async def test_fk_pre_seeding_and_counterparty_integrity():
    """
    Test 2.2: Verifies that IngestionPipeline automatically seeds parent business,
    bank accounts, shareholders, and counterparties so that no foreign key constraint
    is violated even when starting with a completely empty database.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    biz_id = uuid4()
    acc_id = uuid4()

    # Statement references unknown counterparty '400400400'
    statement_csv = b"Data,Suma,Detalii,CUI\n2025-02-01,12000.00,Venit prestari servicii,400400400\n"

    # Invoice references completely different unknown counterparty '500500500'
    invoices_csv = (
        b"numar_factura,data_emiterii,termen_plata,suma_totala,directie,status,cui_furnizor\n"
        b"INV-01,2025-02-01,2025-03-01,5000.00,INTRARE,ACHITAT,500500500\n"
    )

    metadata = {
        "business_id": biz_id,
        "account_id": acc_id,
        "company_name": "Tech Consult SRL",
        "tax_id": "1002223334445",
        "sector_code": "6201",
    }

    files = [
        ("bank_statement.csv", statement_csv),
        ("invoices.csv", invoices_csv),
    ]

    result = await pipeline.run(metadata=metadata, files=files)
    assert result.success is True

    # 1. Business record auto-seeded
    biz_rows = [b for b in mock_db._storage["businesses"] if b["business_id"] == biz_id]
    assert len(biz_rows) == 1
    assert biz_rows[0]["legal_name"] == "Tech Consult SRL"

    # 2. Bank account auto-seeded
    acc_rows = [a for a in mock_db._storage["bank_accounts"] if a["account_id"] == acc_id]
    assert len(acc_rows) == 1
    assert acc_rows[0]["business_id"] == biz_id

    # 3. Both counterparties auto-seeded in counterparties table
    cp_rows = [c for c in mock_db._storage["counterparties"] if c["business_id"] == biz_id]
    assert len(cp_rows) >= 2
    cp_legal_names = {c["legal_name"] for c in cp_rows}
    assert "400400400" in cp_legal_names
    assert "500500500" in cp_legal_names

    # 4. Invoices and transactions point to actual existing counterparties
    tx = mock_db._storage["transactions"][0]
    inv = mock_db._storage["invoices"][0]
    assert tx["counterparty_id"] in [c["counterparty_id"] for c in cp_rows]
    assert inv["counterparty_id"] in [c["counterparty_id"] for c in cp_rows]


@pytest.mark.asyncio
async def test_ingestion_transactional_rollback_on_corrupt_doc():
    """
    Test 2.3: When a document bundle contains a valid bank statement + corrupt invoices file
    under strict=True mode, the pipeline must raise ParsingError and persist 0 records
    (zero dirty partial state in the database).
    """
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    biz_id = uuid4()
    acc_id = uuid4()

    valid_statement = b"Data,Suma,Detalii,CUI\n2025-01-10,5000.00,Test Payment,1001\n"
    corrupt_invoices = b"unrelated,header,only\n1,2,3\n"  # Missing counterparty_name & gross_amount

    metadata = {
        "business_id": biz_id,
        "account_id": acc_id,
        "company_name": "Rollback Test SRL",
        "tax_id": "1001119998887",
    }

    files = [
        ("extras_valid.csv", valid_statement),
        ("invoices_corrupt.csv", corrupt_invoices),
    ]

    with pytest.raises(ParsingError):
        await pipeline.run(metadata=metadata, files=files, strict=True)

    # Verify that NO transactions, invoices, or obligations were committed
    assert len(mock_db._storage["transactions"]) == 0
    assert len(mock_db._storage["invoices"]) == 0
    assert len(mock_db._storage["credit_obligations"]) == 0


@pytest.mark.asyncio
async def test_ingestion_idempotency_duplicate_submission():
    """
    Test 2.4: Running IngestionPipeline twice with identical documents and business_id
    does not create duplicate business records or corrupt relational state.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    biz_id = uuid4()
    acc_id = uuid4()

    csv_data = b"Data,Suma,Detalii,CUI\n2025-01-10,1000.00,Payment A,1001\n"

    metadata = {
        "business_id": biz_id,
        "account_id": acc_id,
        "company_name": "Idempotent Biz SRL",
        "tax_id": "1005556667778",
    }

    # Run 1
    res1 = await pipeline.run(metadata=metadata, files=[("statement.csv", csv_data)])
    assert res1.success is True

    # Run 2 with same business_id and account_id
    res2 = await pipeline.run(metadata=metadata, files=[("statement.csv", csv_data)])
    assert res2.success is True

    # Exactly 1 business record and 1 bank_account record exists
    biz_rows = [b for b in mock_db._storage["businesses"] if b["business_id"] == biz_id]
    assert len(biz_rows) == 1

    acc_rows = [a for a in mock_db._storage["bank_accounts"] if a["account_id"] == acc_id]
    assert len(acc_rows) == 1


@pytest.mark.asyncio
async def test_idempotency_by_tax_id_without_explicit_business_id():
    """Validates idempotency when business_id is omitted: resolves existing business by tax_id."""
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    csv_data = b"Data,Suma,Detalii,CUI\n2025-01-10,1000.00,Payment A,1001\n"
    meta = {"tax_id": "1009998887776", "company_name": "TaxIdemp S.R.L."}

    res1 = await pipeline.run(metadata=meta, files=[("statement.csv", csv_data)])
    assert res1.success is True

    res2 = await pipeline.run(metadata=meta, files=[("statement.csv", csv_data)])
    assert res2.success is True

    assert res1.business_id == res2.business_id
    biz_rows = [b for b in mock_db._storage["businesses"] if b["tax_id"] == "1009998887776"]
    assert len(biz_rows) == 1


@pytest.mark.asyncio
async def test_external_intel_ddl_constraints_and_physical_write():
    """Validates absence of sleep, strict PostgreSQL DDL constraints, and physical table writes."""
    import inspect
    import fintech_app.ingestion.external_intel as ext_module

    # 1. Zero sleep check
    src = inspect.getsource(ext_module)
    assert "sleep" not in src, "asyncio.sleep found in external_intel.py"

    # 2. Pipeline run with external intel persistence
    mock_db = MockDatabase()
    await mock_db.open()
    pipeline = IngestionPipeline(db=mock_db)

    async def mock_collect_all(meta):
        return {
            "business_id": meta.get("business_id"),
            "tax_id": meta.get("tax_id"),
            "reputation": {
                "reputation_sentiment": -2.5,  # Edge value: must clamp to -1.000
                "active_lawsuits_count": 3,
                "total_claim_amount": Decimal("100000.00"),
                "sanctions_flag": False,
            },
            "macro_metrics": {
                "industry_code": "G46",
                "gdp_growth_rate": Decimal("0.035"),  # 3.5% fractional -> 3.50%
                "sector_default_probability": Decimal("0.025"),  # 2.5% fractional -> 2.50%
                "risk_outlook_score": 99,  # Must clamp to 10
            },
            "success": True,
        }

    pipeline.external_intel.collect_all = mock_collect_all

    res = await pipeline.run(
        metadata={"tax_id": "1007778889990", "company_name": "Intel S.R.L.", "sector_code": "G46"},
        files=[("statement.csv", b"Data,Suma,Detalii,CUI\n2025-01-10,500.00,Test,1001\n")],
    )
    assert res.success is True

    # Validate physical write & DDL constraints in web_reputation
    reps = mock_db._storage.get("web_reputation", [])
    assert len(reps) >= 1
    assert reps[0]["news_sentiment_score"] == Decimal("-1.000")
    assert reps[0]["business_id"] == res.business_id

    # Validate physical write & DDL constraints in macro_sector_metrics
    macros = mock_db._storage.get("macro_sector_metrics", [])
    assert len(macros) >= 1
    assert macros[0]["risk_outlook_score"] == 10
    assert macros[0]["sector_growth_rate_yoy"] == Decimal("3.50")
    assert macros[0]["sector_default_rate"] == Decimal("2.50")
