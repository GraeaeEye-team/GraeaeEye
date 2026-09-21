"""
Integration tests for financial underwriting pipeline, contrasting profiles,
degraded execution on missing critical data, and fixture seeding idempotency.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os
import sys
from typing import Any
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline
from ..scripts.seed_fixtures import seed_profile


@pytest.mark.asyncio
async def test_good_sme_score_range():
    """
    1. test_good_sme_score_range:
       Seed GOOD_SME -> run pipeline -> assert universal_score >= 75,
       verdict in [PRIME_LOW_RISK, MODERATE_MONITORED].
    """
    db = MockDatabase()
    await db.open()
    pipeline = UnderwritingAnalyticalPipeline()

    try:
        good_biz_id = await seed_profile("good_sme", db)
        assert good_biz_id is not None

        good_res = await pipeline.run_analysis_from_db(db, good_biz_id)
        assert good_res.scoring_result is not None

        score = good_res.scoring_result.universal_score
        verdict = good_res.scoring_result.verdict_category

        assert score >= 75.0, f"GOOD_SME score {score} was not >= 75.0"
        assert verdict in [
            "PRIME_LOW_RISK",
            "MODERATE_MONITORED",
        ], f"Unexpected verdict for GOOD_SME: {verdict}"
        assert good_res.scoring_result.recommendation == "APPROVED"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_risky_sme_score_range():
    """
    2. test_risky_sme_score_range:
       Seed RISKY_SME -> run pipeline -> assert universal_score <= 55,
       verdict in [HIGH_RISK_REJECT, MODERATE_MONITORED].
    """
    db = MockDatabase()
    await db.open()
    pipeline = UnderwritingAnalyticalPipeline()

    try:
        risky_biz_id = await seed_profile("risky_sme", db)
        assert risky_biz_id is not None

        risky_res = await pipeline.run_analysis_from_db(db, risky_biz_id)
        assert risky_res.scoring_result is not None

        score = risky_res.scoring_result.universal_score
        verdict = risky_res.scoring_result.verdict_category

        assert score <= 55.0, f"RISKY_SME score {score} was not <= 55.0"
        assert verdict in [
            "HIGH_RISK_REJECT",
            "MODERATE_MONITORED",
        ], f"Unexpected verdict for RISKY_SME: {verdict}"
        assert risky_res.scoring_result.recommendation in ["REJECTED", "MANUAL_REVIEW"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_score_contrast():
    """
    3. test_score_contrast:
       Assert GOOD_SME - RISKY_SME >= 20 points.
    """
    db = MockDatabase()
    await db.open()
    pipeline = UnderwritingAnalyticalPipeline()

    try:
        good_id = await seed_profile("good_sme", db)
        risky_id = await seed_profile("risky_sme", db)

        good_res = await pipeline.run_analysis_from_db(db, good_id)
        risky_res = await pipeline.run_analysis_from_db(db, risky_id)

        good_score = good_res.scoring_result.universal_score
        risky_score = risky_res.scoring_result.universal_score
        diff = good_score - risky_score

        assert (
            diff >= 20.0
        ), f"Expected score contrast >= 20 points, got {diff:.2f} (GOOD={good_score}, RISKY={risky_score})"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_missing_critical_data_triggers_manual_review():
    """
    4. test_missing_critical_data_triggers_manual_review:
       Seed business with only transactions (no invoices, obligations, shareholders) ->
       run pipeline -> assert status DEGRADED AND recommendation in [MANUAL_REVIEW, HIGH_RISK_REJECT] (not APPROVED).
    """
    db = MockDatabase()
    await db.open()
    pipeline = UnderwritingAnalyticalPipeline()

    try:
        biz_id = uuid4()
        user_id = uuid4()
        run_id = uuid4()

        # Seed business identity
        await db.add_record_to_businesses(
            tax_id="9998887776665",
            legal_name="Sparse Data Enterprise SRL",
            industry_code="G46",
            registration_date=date(2022, 1, 1),
            business_id=biz_id,
        )

        # Register run in analysis_runs
        await db.add_record_to_analysis_runs(
            user_id=user_id,
            input_company_name="Sparse Data Enterprise SRL",
            input_tax_id="9998887776665",
            input_industry_code="G46",
            files_manifest={},
            active_submodules=[],
            status="QUEUED",
            business_id=biz_id,
            run_id=run_id,
        )

        # Seed ONLY transaction records (no accounts, invoices, obligations, shareholders)
        acc_id = uuid4()
        await db.add_record_to_transactions(
            business_id=biz_id,
            account_id=acc_id,
            timestamp=datetime.now(),
            amount=Decimal("15000.00"),
            direction="INFLOW",
            category="CLIENT_REVENUE",
            liquidity_class="IMMEDIATE_CASH",
        )

        # Execute analytical pipeline
        pipeline_res = await pipeline.run_analysis_from_db(db, biz_id, run_id=run_id)

        # Verify run record status updated to DEGRADED in database
        check_run = await db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
        assert check_run.success and check_run.data
        persisted_status = check_run.data.get("status")
        assert persisted_status == "DEGRADED", f"Expected DEGRADED status, got {persisted_status}"

        # Assert recommendation is MANUAL_REVIEW or HIGH_RISK_REJECT, and strictly NOT APPROVED
        rec = pipeline_res.scoring_result.recommendation
        assert rec in [
            "MANUAL_REVIEW",
            "HIGH_RISK_REJECT",
            "REJECTED",
        ], f"Expected non-approval recommendation, got {rec}"
        assert rec != "APPROVED", "Incomplete data snapshot must not receive APPROVED recommendation"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_idempotent_fixture_seeding(capsys: Any):
    """
    5. test_idempotent_fixture_seeding:
       Run seed_fixtures twice -> second run skips and prints 'exists'.
    """
    db = MockDatabase()
    await db.open()

    try:
        # First seeding run
        id1_good = await seed_profile("good_sme", db)
        id1_risky = await seed_profile("risky_sme", db)
        assert id1_good is not None
        assert id1_risky is not None

        out1 = capsys.readouterr().out
        assert "Seeded profile 'good_sme'" in out1
        assert "Seeded profile 'risky_sme'" in out1
        assert len(db._storage["businesses"]) == 2

        # Second seeding run (idempotency check)
        id2_good = await seed_profile("good_sme", db)
        id2_risky = await seed_profile("risky_sme", db)

        out2 = capsys.readouterr().out
        assert "exists" in out2
        assert "already exists in database" in out2

        # Verify returned UUIDs match and no duplicate rows were inserted
        assert id1_good == id2_good
        assert id1_risky == id2_risky
        assert len(db._storage["businesses"]) == 2
    finally:
        await db.close()
