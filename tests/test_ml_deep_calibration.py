"""
Test Module 3: Deep ML Engine Calibration & Selective Submodule Execution.
Validates:
- Dynamic weight renormalization across active submodules (sum = 1.0, score in [0, 100]).
- CashflowStabilityEvaluator fallback on general INFLOW when CLIENT_REVENUE is absent.
- MacroSectorRiskEvaluator fallback hierarchy (specific NACE -> 'DEFAULT' -> baseline).
- Probability of Default (PD) logistic transformation and boundary clamping [0.001, 0.999].
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ml.base import EvaluationStatus
from fintech_app.ml.loader import CompanyDataLoader
from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline
from fintech_app.ml.scoring import CreditScoringEngine
from fintech_app.ml.submodule_cash_stability import CashflowStabilityEvaluator
from fintech_app.ml.submodule_macro import MacroSectorRiskEvaluator


# =============================================================================
# 3.1. SELECTIVE SUBMODULE EXECUTION & WEIGHT RENORMALIZATION
# =============================================================================


def test_selective_submodules_and_weight_renormalization():
    """
    Test 3.1: Validates that when only a subset of submodules is requested (e.g. OS, ICR, CFS),
    the CreditScoringEngine dynamically renormalizes weights to sum to exactly 1.0,
    and produces an overall score properly bounded in [0, 100].
    """
    engine = CreditScoringEngine()

    # Active submodules: OS (weights: 0.08), ICR (0.15), CFS (0.08). Total = 0.31
    active_codes = ["OS", "ICR", "CFS"]
    base_sum = sum(engine.SUBMODULE_WEIGHTS[c] for c in active_codes)
    assert round(base_sum, 4) == 0.31

    # Canonical 18-element feature vector: indices populated ONLY for OS (0,1), ICR (9,10), CFS (11,12)
    # All other 12 indices set to None
    fv: list[float | None] = [None] * 18
    fv[0] = 80.0  # OS: Ownership_Dispersion_Index
    fv[1] = 70.0  # OS: Governance_Independence_Index (avg OS = 75.0)
    fv[9] = 90.0  # ICR: Cash_Readiness_Index
    fv[10] = 80.0  # ICR: Runway_Buffer_Index (avg ICR = 85.0)
    fv[11] = 60.0  # CFS: Revenue_Predictability_Index
    fv[12] = 60.0  # CFS: Revenue_Trajectory_Index (avg CFS = 60.0)

    result = engine.calculate_score(feature_vector=fv)

    # Expected renormalized weights:
    # w_OS = 0.08 / 0.31 = 0.25806
    # w_ICR = 0.15 / 0.31 = 0.48387
    # w_CFS = 0.08 / 0.31 = 0.25806
    w_os = 0.08 / 0.31
    w_icr = 0.15 / 0.31
    w_cfs = 0.08 / 0.31

    expected_score = (w_os * 75.0) + (w_icr * 85.0) + (w_cfs * 60.0)
    expected_score_rounded = round(expected_score, 2)

    assert 0.0 <= result.investment_attractiveness_score <= 100.0
    assert result.investment_attractiveness_score == expected_score_rounded
    assert result.verdict_category == "PRIME_LOW_RISK"
    assert result.recommendation == "APPROVED"


def test_selective_submodules_in_analytical_pipeline():
    """Validates that UnderwritingAnalyticalPipeline only executes the requested active_submodules."""
    pipeline = UnderwritingAnalyticalPipeline()
    biz_id = uuid4()

    # Create synthetic snapshot with basic records
    snapshot = SimpleNamespace(
        business=SimpleNamespace(
            business_id=biz_id,
            industry_code="6201",
            registration_date=date(2020, 1, 1),
            total_board_seats=3,
            independent_directors_count=1,
        ),
        shareholders=[
            SimpleNamespace(shareholder_name="Founder", equity_percentage=Decimal("70.00"), is_management_member=True),
            SimpleNamespace(
                shareholder_name="Investor", equity_percentage=Decimal("30.00"), is_management_member=False
            ),
        ],
        reputation=SimpleNamespace(
            active_lawsuits_count=0,
            total_claim_amount=Decimal("0.00"),
            is_in_sanctions_list=False,
            sentiment_score=0.8,
            monthly_traffic=15000,
        ),
        macro_metrics=None,
        macro_sector_metrics=None,
        counterparties=[],
        invoices=[],
        credit_facilities=[],
        credit_obligations=[],
        transactions=[],
        bank_accounts=[],
        as_of_date=date.today(),
    )

    # Request only OS and WPR
    res = pipeline.run_analysis(snapshot=snapshot, active_submodules=["OS", "WPR"])

    assert "OS" in res.submodule_results
    assert "WPR" in res.submodule_results

    # Unrequested submodules are marked as SKIPPED with None indices
    assert res.submodule_results["MSR"].verdict == "SKIPPED"
    assert all(v is None for v in res.submodule_results["MSR"].indices.values())
    assert res.submodule_results["CFS"].verdict == "SKIPPED"
    assert all(v is None for v in res.submodule_results["CFS"].indices.values())

    assert 0.0 <= res.scoring_result.investment_attractiveness_score <= 100.0


# =============================================================================
# 3.2. CASHFLOW STABILITY FALLBACK ON GENERAL INFLOW
# =============================================================================


def test_cashflow_stability_fallback_on_general_inflow():
    """
    Test 3.2: When incoming transactions lack the explicit category 'CLIENT_REVENUE'
    or 'REVENUE', CashflowStabilityEvaluator must gracefully fall back to general
    INFLOW transactions rather than aborting with DATA_ABSENT or producing 0 score.
    """
    evaluator = CashflowStabilityEvaluator()
    ref_date = date.today()

    # Create 12 months of transactions with direction='INFLOW' but category='OTHER_INCOMING'
    txs = []
    for i in range(12):
        tx_dt = ref_date - timedelta(days=i * 30)
        txs.append(
            SimpleNamespace(
                transaction_date=tx_dt,
                timestamp=datetime.combine(tx_dt, datetime.min.time()),
                amount=Decimal("15000.00"),
                direction="INFLOW",
                category="OTHER_INFLOW",  # Not CLIENT_REVENUE!
            )
        )

    snapshot = SimpleNamespace(
        transactions=txs,
        as_of_date=ref_date,
    )

    result = evaluator.evaluate(snapshot)

    assert result.status == EvaluationStatus.SUCCESS
    assert result.indices["Revenue_Predictability_Index"] is not None
    assert result.indices["Revenue_Trajectory_Index"] is not None
    assert result.indices["Revenue_Predictability_Index"] > 50.0


# =============================================================================
# 3.3. MACRO SECTOR FALLBACK HIERARCHY
# =============================================================================


@pytest.mark.asyncio
async def test_macro_sector_fallback_hierarchy():
    """
    Test 3.3: When a company has an unknown or non-existent sector code (e.g. 'UNKNOWN_999'),
    CompanyDataLoader falls back to 'DEFAULT' or the first available macro record,
    and MacroSectorRiskEvaluator produces a valid assessment without crashing.
    """
    mock_db = MockDatabase()
    await mock_db.open()
    loader = CompanyDataLoader(db=mock_db)

    biz_id = uuid4()

    # Seed business with unknown sector
    await mock_db.add_record_to_businesses(
        business_id=biz_id,
        legal_name="Unknown Sector Corp",
        tax_id="1009990001112",
        industry_code="UNKNOWN_999",
        registration_date=date(2021, 5, 1),
    )

    # Seed macro sector metric under 'DEFAULT' fallback code
    await mock_db.add_record_to_macro_sector_metrics(
        industry_code="DEFAULT",
        reference_date=date.today(),
        sector_growth_rate_yoy=Decimal("4.50"),
        sector_default_rate=Decimal("2.10"),
        risk_outlook_score=3,
    )

    snapshot = await loader.load_snapshot(business_id=biz_id)
    assert snapshot is not None
    assert snapshot.macro_sector_metrics is not None

    evaluator = MacroSectorRiskEvaluator()
    eval_res = evaluator.evaluate(snapshot)

    assert eval_res.status == EvaluationStatus.SUCCESS
    assert eval_res.indices["Sector_Vitality_Index"] is not None
    assert 0.0 <= eval_res.indices["Sector_Vitality_Index"] <= 100.0


# =============================================================================
# 3.4. EXTREME SCENARIOS & PROBABILITY OF DEFAULT (PD) CLAMPING
# =============================================================================


def test_extreme_scenarios_and_pd_clamping():
    """
    Test 3.4: Tests extreme credit conditions and verifies logistic PD calibration:
    - Pristine business (Score ~ 100): low PD <= 0.05, clamped to [0.001, 0.999].
    - Catastrophic business (Score ~ 0): high PD >= 0.80, clamped to [0.001, 0.999].
    - Out-of-bounds scores (-100, 200) strictly bounded to [0.001, 0.999].
    """
    engine = CreditScoringEngine()

    # 1. Pristine profile
    score_pristine = 100.0
    pd_pristine = engine.calculate_probability_of_default(score_pristine)
    assert isinstance(pd_pristine, float)
    assert 0.001 <= pd_pristine <= 0.05

    # 2. Catastrophic profile
    score_catastrophic = 0.0
    pd_catastrophic = engine.calculate_probability_of_default(score_catastrophic)
    assert isinstance(pd_catastrophic, float)
    assert 0.80 <= pd_catastrophic <= 0.999

    # 3. Monotonicity: Higher score must always yield strictly lower or equal PD
    scores = [0.0, 20.0, 40.0, 50.0, 60.0, 80.0, 100.0]
    pds = [engine.calculate_probability_of_default(s) for s in scores]
    for i in range(len(pds) - 1):
        assert pds[i] >= pds[i + 1], f"Monotonicity violation at score {scores[i]}: {pds[i]} < {pds[i+1]}"

    # 4. Out-of-bounds safety clamping
    assert engine.calculate_probability_of_default(-999.0) == 0.999
    assert engine.calculate_probability_of_default(999.0) == 0.001
