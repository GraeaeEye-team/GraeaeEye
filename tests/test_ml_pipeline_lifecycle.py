"""
Automated Test Suite: ML Pipeline Lifecycle, Extended Timeout & Real-Time Heartbeat Telemetry.

Validates:
1. End-to-end execution of `UnderwritingAnalyticalPipeline.run_analysis_from_db`:
   - CompanyDataSnapshot loading via CompanyDataLoader from relational graph.
   - Autonomous 9-submodule evaluation.
   - CreditScoringEngine scoring & prompt compilation.
   - Anti-freeze Heartbeat logging telemetry ([LLM_START], periodic [LLM_HEARTBEAT], [LLM_SUCCESS]).
   - Clean background worker task cancellation without leaking CancelledError.
   - analysis_runs terminal persistence (COMPLETED, universal_score, llm_final_summary, completed_at).
2. Strict timeout enforcement with automatic fallback degradation on slow/hanging executor.
3. Fault-tolerant heartbeat: temporary database logging errors do not terminate heartbeat loop.
4. Selective submodule execution (active_submodules) triggering DEGRADED status appropriately.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline


from fintech_app.ingestion.pipeline import IngestionPipeline


async def seed_full_company_graph(mock_db: MockDatabase, biz_id: UUID, run_id: UUID) -> None:
    """Seeds a complete relational company graph into MockDatabase using IngestionPipeline."""
    user_id = uuid4()
    await mock_db.add_record_to_users(
        user_id=user_id,
        email="analyst@graeae.eye",
        password_hash="mock_hash",
        full_name="Lead Credit Underwriter",
        role="ANALYST",
        is_active=True,
    )

    await mock_db.add_record_to_businesses(
        business_id=biz_id,
        tax_id="1009988776655",
        legal_name="Moldova Agro Logistics SRL",
        industry_code="0111",
        registration_date=date(2020, 1, 15),
        total_board_seats=3,
        independent_directors_count=1,
    )

    statement_csv = (
        "Data,Suma,Detalii,CUI\n"
        "2026-01-05,145000.00,Incasare factura vanzari cereale,100100100\n"
        "2026-01-10,-38000.00,Achitare furnizor ingrasaminte,200200200\n"
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
        "Victoriabank,TERM_LOAN,150000.00,42000.00,3200.00,0,0\n"
    ).encode("utf-8")

    ingestion_pipe = IngestionPipeline(db=mock_db)
    meta = {
        "business_id": biz_id,
        "tax_id": "1009988776655",
        "company_name": "Moldova Agro Logistics SRL",
        "sector_code": "0111",
    }
    files = [
        ("extras_cont.csv", statement_csv),
        ("facturi_fiscale.csv", invoices_csv),
        ("credite_bancare.csv", credits_csv),
    ]
    ingest_res = await ingestion_pipe.run(metadata=meta, files=files)
    assert ingest_res.success is True

    await mock_db.add_record_to_analysis_runs(
        run_id=run_id,
        user_id=user_id,
        business_id=biz_id,
        input_company_name="Moldova Agro Logistics SRL",
        input_tax_id="1009988776655",
        input_industry_code="0111",
        files_manifest={"files": ["extras_cont.csv", "facturi_fiscale.csv", "credite_bancare.csv"]},
        active_submodules=["OS", "WPR", "MSR", "CD", "SD", "ICR", "CFS", "RQ", "ICDL"],
        status="QUEUED",
    )


@pytest.mark.asyncio
async def test_pipeline_lifecycle_with_heartbeat():
    """
    Test 1: Full end-to-end lifecycle verification with simulated slow inference:
    - Verifies [LLM_START] emission before synthesis.
    - Verifies periodic [LLM_HEARTBEAT] logs emitted during slow inference.
    - Verifies [LLM_SUCCESS] on completion.
    - Verifies clean heartbeat worker cancellation without CancelledError.
    - Verifies analysis_runs status COMPLETED, universal_score > 0, and llm_final_summary persisted.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    biz_id = uuid4()
    run_id = uuid4()
    await seed_full_company_graph(mock_db, biz_id, run_id)

    async def delayed_mock_executor(prompt: str, model: str, **kwargs: Any) -> str:
        # Simulates 1.8s inference time for local Ollama
        await asyncio.sleep(1.8)
        return (
            "## SIMULATED UNDERWRITING MEMORANDUM\n"
            "Enterprise demonstrates superior debt service capability. Approved unconditionally."
        )

    pipeline = UnderwritingAnalyticalPipeline()
    result = await pipeline.run_analysis_from_db(
        db=mock_db,
        business_id=biz_id,
        run_id=run_id,
        executor=delayed_mock_executor,
        timeout=10.0,
        heartbeat_interval=0.4,  # Fast interval for unit test (emits ~4 heartbeats in 1.8s)
    )

    assert result is not None
    assert result.scoring_result is not None

    # 1. Assert analysis_runs row
    run_rep = await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
    assert run_rep.success and run_rep.data
    run_data = run_rep.data
    assert run_data["status"] == "COMPLETED"
    assert run_data["universal_score"] > Decimal("0")
    assert "SIMULATED UNDERWRITING MEMORANDUM" in run_data["llm_final_summary"]
    assert run_data["completed_at"] is not None
    assert "delayed_mock_executor" in run_data["raw_indices_payload"]["_synthesis_engine"]

    # 2. Assert analysis_logs records
    logs_rep = await mock_db.get_records_from_analysis_logs(run_id=run_id)
    assert logs_rep.success and logs_rep.data
    logs = logs_rep.data

    llm_logs = [l for l in logs if l.get("stage") == "LLM_SYNTHESIS"]
    messages = [l.get("message", "") for l in llm_logs]

    # Verify [LLM_START]
    start_logs = [m for m in messages if "[LLM_START]" in m]
    assert len(start_logs) == 1, f"Expected 1 [LLM_START], got {start_logs}"
    assert "delayed_mock_executor" in start_logs[0]

    # Verify [LLM_HEARTBEAT]
    hb_logs = [m for m in messages if "[LLM_HEARTBEAT]" in m]
    assert len(hb_logs) >= 2, f"Expected >= 2 [LLM_HEARTBEAT] messages, got {len(hb_logs)}: {hb_logs}"
    assert all("лимит 10с" in m for m in hb_logs)

    # Verify [LLM_SUCCESS]
    success_logs = [m for m in messages if "[LLM_SUCCESS]" in m]
    assert len(success_logs) == 1, f"Expected 1 [LLM_SUCCESS], got {success_logs}"
    assert "символов" in success_logs[0]

    # Verify final PIPELINE_COMPLETE
    complete_logs = [l for l in logs if l.get("stage") == "PIPELINE_COMPLETE"]
    assert len(complete_logs) == 1


@pytest.mark.asyncio
async def test_pipeline_lifecycle_timeout_graceful_fallback():
    """
    Test 2: Validates that when executor hangs longer than configured timeout,
    the pipeline strictly enforces deadline, falls back to structured template,
    emits LLM_FALLBACK_TRIGGERED warning, and completes successfully without crashing.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    biz_id = uuid4()
    run_id = uuid4()
    await seed_full_company_graph(mock_db, biz_id, run_id)

    async def hanging_mock_executor(prompt: str, model: str, **kwargs: Any) -> str:
        # Hangs for 4 seconds, exceeding 0.4s timeout
        await asyncio.sleep(4.0)
        return "Unreachable text"

    pipeline = UnderwritingAnalyticalPipeline()
    result = await pipeline.run_analysis_from_db(
        db=mock_db,
        business_id=biz_id,
        run_id=run_id,
        executor=hanging_mock_executor,
        timeout=0.4,  # Enforce strict 0.4s timeout
        heartbeat_interval=0.1,
    )

    assert result is not None

    # Verify analysis_runs status and fallback memorandum
    run_rep = await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
    assert run_rep.success and run_rep.data
    run_data = run_rep.data
    assert run_data["status"] == "COMPLETED"
    assert "CREDIT COMMITTEE UNDERWRITING MEMORANDUM" in run_data["llm_final_summary"]
    assert run_data["raw_indices_payload"]["_synthesis_engine"] == "fallback:template"

    # Verify analysis_logs
    logs_rep = await mock_db.get_records_from_analysis_logs(run_id=run_id)
    assert logs_rep.success and logs_rep.data
    logs = logs_rep.data
    llm_logs = [l for l in logs if l.get("stage") == "LLM_SYNTHESIS"]
    severities = [l.get("severity") for l in llm_logs]
    assert "WARN" in severities

    fallback_logs = [l for l in llm_logs if "LLM_FALLBACK_TRIGGERED" in l.get("message", "")]
    assert len(fallback_logs) >= 1


@pytest.mark.asyncio
async def test_fault_tolerant_heartbeat_db_resilience():
    """
    Test 3: Validates that intermittent database errors during add_record_to_analysis_logs
    do NOT kill the background heartbeat worker task.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    biz_id = uuid4()
    run_id = uuid4()
    await seed_full_company_graph(mock_db, biz_id, run_id)

    call_count = 0
    orig_add_record = mock_db.add_record_to_analysis_logs

    async def flaky_add_record(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        # Flake once on stage LLM_SYNTHESIS with heartbeat
        if kwargs.get("stage") == "LLM_SYNTHESIS" and "[LLM_HEARTBEAT]" in kwargs.get("message", ""):
            if call_count == 2:
                raise RuntimeError("Temporary DB connection pool hiccup")
        return await orig_add_record(**kwargs)

    mock_db.add_record_to_analysis_logs = flaky_add_record  # type: ignore

    async def slow_executor(prompt: str, model: str, **kwargs: Any) -> str:
        await asyncio.sleep(1.2)
        return "Resilient response"

    pipeline = UnderwritingAnalyticalPipeline()
    await pipeline.run_analysis_from_db(
        db=mock_db,
        business_id=biz_id,
        run_id=run_id,
        executor=slow_executor,
        timeout=5.0,
        heartbeat_interval=0.3,
    )

    logs_rep = await mock_db.get_records_from_analysis_logs(run_id=run_id)
    hb_logs = [l for l in logs_rep.data if "[LLM_HEARTBEAT]" in l.get("message", "")]
    # Verify that despite 1 error, subsequent heartbeats were still emitted
    assert len(hb_logs) >= 2


@pytest.mark.asyncio
async def test_pipeline_selective_submodules_degraded_status():
    """
    Test 4: Validates that executing a restricted subset of submodules (e.g. OS, ICR)
    properly produces DEGRADED status in analysis_runs while preserving valid scoring.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    biz_id = uuid4()
    run_id = uuid4()
    await seed_full_company_graph(mock_db, biz_id, run_id)

    async def selective_executor(prompt: str, model: str, **kw: Any) -> str:
        return "Selective Underwriting Memo"

    pipeline = UnderwritingAnalyticalPipeline()
    result = await pipeline.run_analysis_from_db(
        db=mock_db,
        business_id=biz_id,
        run_id=run_id,
        active_submodules=["OS", "ICR"],
        executor=selective_executor,
    )

    assert result is not None
    run_rep = await mock_db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
    assert run_rep.success and run_rep.data
    run_data = run_rep.data
    # With 7 submodules skipped/DATA_ABSENT, final status must be DEGRADED
    assert run_data["status"] == "DEGRADED"
    assert run_data["universal_score"] > Decimal("0")
    assert run_data["llm_final_summary"] == "Selective Underwriting Memo"
