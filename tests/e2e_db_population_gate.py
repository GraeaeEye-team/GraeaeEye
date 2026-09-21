"""
End-to-End Database Population Gate (Module 6 Verification).

Performs an end-to-end run ingesting all multi-document assets:
- Bank statement CSV
- Invoices CSV
- Credit obligations CSV
- User registration & preferences
- External intelligence (web reputation & macro metrics)
- ML scoring, LLM synthesis & telemetry logging

Verifies and snapshots count(*) for all 13 canonical tables:
1. businesses
2. bank_accounts
3. counterparties
4. transactions
5. invoices
6. credit_obligations
7. shareholders
8. web_reputation
9. macro_sector_metrics
10. users
11. user_settings
12. analysis_runs
13. analysis_logs
"""

from __future__ import annotations

import asyncio
from datetime import date
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.auth.security import hash_password
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ingestion.pipeline import IngestionPipeline
from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline


async def run_population_gate():
    print("\n" + "=" * 60)
    print("🚀 MODULE 6: END-TO-END DATABASE POPULATION GATE RUNNER")
    print("=" * 60)

    db = MockDatabase()
    await db.open()

    # 1. Seed User and User Settings (Tables: users, user_settings)
    user_id = uuid4()
    await db.add_record_to_users(
        user_id=user_id,
        email="chief.auditor@graeae.eye",
        password_hash=hash_password("SuperAuditPassword2026!"),
        full_name="Chief Compliance Auditor",
        role="UNDERWRITER",
        is_active=True,
    )
    await db.add_record_to_user_settings(
        user_id=user_id,
        ui_theme="dark",
        terminal_sound_effects=False,
        auto_expand_reports=True,
    )

    # 2. Register Corporate Entity (Table: businesses)
    biz_id = uuid4()
    await db.add_record_to_businesses(
        business_id=biz_id,
        tax_id="1003600099881",
        legal_name="Universal Agro Trade SRL",
        industry_code="G46",
        registration_date=date(2018, 4, 15),
        total_board_seats=3,
        independent_directors_count=1,
    )
    business_id = biz_id

    # 3. Prepare Multi-Document Bundles
    statement_csv = (
        "Data,Suma,Detalii,CUI\n"
        "2026-01-05,45000.00,Incasare factura vanzari cereale,100100100\n"
        "2026-01-10,-18000.00,Achitare furnizor ingrasaminte,200200200\n"
        "2026-01-15,-12500.00,Plata salarii angajati,300300300\n"
    ).encode("utf-8")

    invoices_csv = (
        "numar_factura,data_emiterii,termen_plata,suma_totala,directie,status,cui_furnizor\n"
        "FAC-101,2026-01-05,2026-02-05,45000.00,IESIRE,ACHITAT,100100100\n"
        "FAC-102,2026-01-08,2026-02-08,32000.00,INTRARE,EXPIRAT,200200200\n"
    ).encode("utf-8")

    credits_csv = (
        "creditor,tip_credit,suma_credit,sold,rata_lunara,past_due_30d,past_due_90d\n"
        "Moldova Agroindbank,LINIE_DE_CREDIT,300000.00,85000.00,5400.00,0,0\n"
        "Victoriabank,TERM_LOAN,150000.00,42000.00,3200.00,1,0\n"
    ).encode("utf-8")

    # 4. Ingest Documents into Database Graph
    ingestion_pipe = IngestionPipeline(db=db)
    meta = {
        "business_id": business_id,
        "tax_id": "1003600099881",
        "company_name": "Universal Agro Trade SRL",
        "sector_code": "G46",
    }
    files = [
        ("extras_cont.csv", statement_csv),
        ("facturi_fiscale.csv", invoices_csv),
        ("credite_bancare.csv", credits_csv),
    ]

    ingest_res = await ingestion_pipe.run(metadata=meta, files=files)
    assert ingest_res.success, f"Ingestion failed: {getattr(ingest_res, 'error_message', None)}"

    # 5. Create Analysis Run & Logs (Tables: analysis_runs, analysis_logs)
    run_id = uuid4()
    await db.add_record_to_analysis_runs(
        run_id=run_id,
        user_id=user_id,
        business_id=business_id,
        input_company_name="Universal Agro Trade SRL",
        input_tax_id="1003600099881",
        input_industry_code="G46",
        files_manifest={"files": ["statement.csv", "invoices.csv", "credits.csv"]},
        active_submodules=["OS", "WPR", "MSR", "CD", "SD", "ICR", "CFS", "RQ", "ICDL"],
        status="PROCESSING",
    )
    await db.add_record_to_analysis_logs(
        run_id=run_id,
        severity="INFO",
        stage="INGESTION",
        message="Multi-document packet uploaded and persisted to relational database.",
    )

    # 6. Execute ML Underwriting Pipeline & LLM Synthesis
    ml_pipe = UnderwritingAnalyticalPipeline()
    ml_res = await ml_pipe.run_analysis_from_db(
        db=db,
        business_id=business_id,
        run_id=run_id,
        tax_id="1003600099881",
    )
    assert ml_res.scoring_result is not None, "ML Scoring failed"

    # 7. Collect and Display Final 13-Table Snapshot
    canonical_tables = [
        "businesses",
        "bank_accounts",
        "counterparties",
        "transactions",
        "invoices",
        "credit_obligations",
        "shareholders",
        "web_reputation",
        "macro_sector_metrics",
        "users",
        "user_settings",
        "analysis_runs",
        "analysis_logs",
    ]

    print("\n--- 13-TABLE RELATIONAL GRAPH SNAPSHOT ---")
    print(f"{'Table Name':<26} | {'Count':<8} | {'Status'}")
    print("-" * 50)

    zero_tables = []
    for tbl in canonical_tables:
        rows = db._storage.get(tbl, [])
        count = len(rows)
        status_str = "✅ POPULATED" if count > 0 else "❌ ZERO ROWS"
        if count == 0:
            zero_tables.append(tbl)
        print(f"{tbl:<26} | {count:<8} | {status_str}")

    print("-" * 50)
    if zero_tables:
        print(f"❌ FAILED: Tables with 0 rows: {zero_tables}")
        sys.exit(1)
    else:
        print("🎉 ALL 13 CANONICAL TABLES STRICTLY > 0! Gate verification SUCCESS.")
        print(f"Universal Score: {ml_res.scoring_result.investment_attractiveness_score:.2f}")
        print(f"Risk Verdict:    {ml_res.scoring_result.verdict_category}")
        print(f"Recommendation:  {ml_res.scoring_result.recommendation}")
        print(f"Executive Memo:  {len(ml_res.scoring_result.executive_summary)} chars")


if __name__ == "__main__":
    asyncio.run(run_population_gate())
