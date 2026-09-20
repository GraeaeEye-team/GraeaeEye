"""
Integration tests for GOOD_SME and RISKY_SME financial profile fixtures.
Verifies score ranges, risk verdicts, contrast divergence, and DAL seeding idempotency.
"""

from __future__ import annotations

import os
import sys
from typing import Any
import pytest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline
from scripts.seed_fixtures import seed_profile


@pytest.mark.asyncio
async def test_fixtures_score_ranges_and_contrast():
    """
    Verifies that:
    1. GOOD_SME produces universal_score >= 75 and verdict in [PRIME_LOW_RISK, MODERATE_MONITORED]
    2. RISKY_SME produces universal_score <= 55 and verdict in [HIGH_RISK_REJECT, MODERATE_MONITORED]
    3. The score divergence (GOOD - RISKY) is at least 20 points.
    """
    db = MockDatabase()
    await db.open()
    pipeline = UnderwritingAnalyticalPipeline()

    try:
        # 1. Seed GOOD_SME
        good_biz_id = await seed_profile("good_sme", db)
        assert good_biz_id is not None, "Failed to seed GOOD_SME"

        # 2. Run UnderwritingAnalyticalPipeline for GOOD_SME
        good_result = await pipeline.run_analysis_from_db(db, good_biz_id)
        assert good_result is not None
        assert good_result.scoring_result is not None

        good_score = good_result.scoring_result.universal_score
        good_verdict = good_result.scoring_result.verdict_category

        # 3. Assert GOOD_SME score >= 75
        assert good_score >= 75.0, f"GOOD_SME score {good_score} was not >= 75"

        # 4. Assert GOOD_SME verdict in [PRIME_LOW_RISK, MODERATE_MONITORED]
        assert good_verdict in [
            "PRIME_LOW_RISK",
            "MODERATE_MONITORED",
        ], f"Unexpected verdict for GOOD_SME: {good_verdict}"

        # 5. Seed RISKY_SME
        risky_biz_id = await seed_profile("risky_sme", db)
        assert risky_biz_id is not None, "Failed to seed RISKY_SME"

        # 6. Run UnderwritingAnalyticalPipeline for RISKY_SME
        risky_result = await pipeline.run_analysis_from_db(db, risky_biz_id)
        assert risky_result is not None
        assert risky_result.scoring_result is not None

        risky_score = risky_result.scoring_result.universal_score
        risky_verdict = risky_result.scoring_result.verdict_category

        # 7. Assert RISKY_SME score <= 55
        assert risky_score <= 55.0, f"RISKY_SME score {risky_score} was not <= 55"

        # 8. Assert RISKY_SME verdict in [HIGH_RISK_REJECT, MODERATE_MONITORED]
        assert risky_verdict in [
            "HIGH_RISK_REJECT",
            "MODERATE_MONITORED",
        ], f"Unexpected verdict for RISKY_SME: {risky_verdict}"

        # 9. Assert score difference >= 20 points
        score_diff = good_score - risky_score
        assert (
            score_diff >= 20.0
        ), f"Expected score difference >= 20, got {score_diff:.2f} (GOOD={good_score}, RISKY={risky_score})"

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_fixtures_seeding_idempotency(capsys: Any):
    """
    Verifies that calling seed_profile repeatedly on the same database
    identifies existing records by tax_id, prints 'exists', skips insertion,
    and returns the existing business_id without duplicating database entries.
    """
    db = MockDatabase()
    await db.open()

    try:
        # First seeding run
        good_id_1 = await seed_profile("good_sme", db)
        risky_id_1 = await seed_profile("risky_sme", db)
        assert good_id_1 is not None
        assert risky_id_1 is not None

        captured_1 = capsys.readouterr()
        assert "Seeded profile 'good_sme'" in captured_1.out
        assert "Seeded profile 'risky_sme'" in captured_1.out

        initial_biz_count = len(db._storage["businesses"])
        assert initial_biz_count == 2

        # Second seeding run (idempotency check)
        good_id_2 = await seed_profile("good_sme", db)
        risky_id_2 = await seed_profile("risky_sme", db)

        captured_2 = capsys.readouterr()
        assert "exists" in captured_2.out
        assert "Profile 'good_sme' with tax_id '1001001001001' already exists" in captured_2.out
        assert "Profile 'risky_sme' with tax_id '1002002002002' already exists" in captured_2.out

        # Identical business IDs returned
        assert good_id_1 == good_id_2
        assert risky_id_1 == risky_id_2

        # No duplicate records created in businesses table
        assert len(db._storage["businesses"]) == 2

    finally:
        await db.close()
