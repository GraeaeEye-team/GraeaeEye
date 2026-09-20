"""
Unit tests for the ML-to-API Contract Mapping Layer.

Validates:
1. Exact bijection and ordering between ML FEATURE_NAMES and API CANONICAL_18D_KEYS.
2. Bidirectional mappings for all 9 submodule codes (OS..ICDL <-> OS_4_1..ICDL_4_9).
3. Status and verdict translations for all 3 EvaluationStatus states (SUCCESS, DATA_ABSENT, ERROR).
4. Full end-to-end synthetic ML UnderwritingPipelineResult to AnalysisReportResponse conversion.
5. Error-path handling, degraded status resolution, and critical flag extraction.
"""

import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.api.contract_mapping import (
    API_TO_ML_INDEX_MAP,
    API_TO_ML_SUBMODULE_MAP,
    ML_TO_API_INDEX_MAP,
    ML_TO_API_SUBMODULE_MAP,
    SUBMODULE_NAMES,
    api_index_to_ml,
    api_submodule_to_ml,
    build_llm_synthesis,
    map_ml_result_to_analysis_report,
    map_submodule_status,
    ml_index_to_api,
    ml_submodule_to_api,
)
from fintech_app.api.schemas import (
    CANONICAL_18D_KEYS,
    AnalysisReportResponse,
    AnalysisStatus,
    Recommendation,
    SubmoduleExecutionStatus,
    VerdictCategory,
)
from fintech_app.ml.base import EvaluationStatus, SubmoduleResult
from fintech_app.ml.pipeline import UnderwritingPipelineResult
from fintech_app.ml.scoring import CreditScoringEngine, CreditScoringResult


# =====================================================================
# 1. BIJECTION & EXACT ORDERING OF 18D FEATURE VECTOR KEYS
# =====================================================================

def test_feature_vector_bijection_and_canonical_order():
    """Verifies that ML 18 features map 1:1 and in exact sequence to API keys."""
    ml_names = CreditScoringEngine.FEATURE_NAMES
    api_keys = CANONICAL_18D_KEYS

    assert len(ml_names) == 18, f"Expected exactly 18 ML features, got {len(ml_names)}"
    assert len(api_keys) == 18, f"Expected exactly 18 API keys, got {len(api_keys)}"

    for idx, (ml_feat, api_key) in enumerate(zip(ml_names, api_keys)):
        # Must match via pure lowercasing
        assert ml_feat.lower() == api_key, (
            f"Mismatch at index {idx}: ML '{ml_feat}'.lower() != API '{api_key}'"
        )
        # Check bidirectional helper functions
        assert ml_index_to_api(ml_feat) == api_key
        assert api_index_to_ml(api_key) == ml_feat

    # Verify dictionaries contain all 18 entries
    assert len(ML_TO_API_INDEX_MAP) == 18
    assert len(API_TO_ML_INDEX_MAP) == 18


def test_invalid_index_keys_raise_loudly():
    """Verifies that unknown index keys raise KeyError."""
    with pytest.raises(KeyError):
        ml_index_to_api("NonExistent_Financial_Index")

    with pytest.raises(KeyError):
        api_index_to_ml("non_existent_financial_index")


# =====================================================================
# 2. ALL 9 SUBMODULE CODE MAPPINGS (FORWARD & REVERSE)
# =====================================================================

EXPECTED_SUBMODULE_PAIRS = [
    ("OS", "OS_4_1"),
    ("WPR", "WPR_4_2"),
    ("MSR", "MSR_4_3"),
    ("CD", "CD_4_4"),
    ("SD", "SD_4_5"),
    ("ICR", "ICR_4_6"),
    ("CFS", "CFS_4_7"),
    ("RQ", "RQ_4_8"),
    ("ICDL", "ICDL_4_9"),
]


def test_all_nine_submodule_code_mappings():
    """Verifies forward and reverse mappings for all 9 analytical submodules."""
    assert len(EXPECTED_SUBMODULE_PAIRS) == 9

    for short_code, long_id in EXPECTED_SUBMODULE_PAIRS:
        # Forward mapping
        assert ml_submodule_to_api(short_code) == long_id
        assert ML_TO_API_SUBMODULE_MAP[short_code] == long_id

        # Reverse mapping
        assert api_submodule_to_ml(long_id) == short_code
        assert API_TO_ML_SUBMODULE_MAP[long_id] == short_code

        # Name mapping exists
        assert short_code in SUBMODULE_NAMES
        assert len(SUBMODULE_NAMES[short_code]) > 0


def test_invalid_submodule_code_raises_loudly():
    """Verifies that unknown submodule identifiers raise KeyError."""
    with pytest.raises(KeyError):
        ml_submodule_to_api("UNKNOWN_CODE")

    with pytest.raises(KeyError):
        api_submodule_to_ml("UNKNOWN_4_99")


# =====================================================================
# 3. STATUS & VERDICT MAPPINGS (ALL 3 EVALUATION STATES)
# =====================================================================

def test_status_mapping_success():
    """EvaluationStatus.SUCCESS -> SubmoduleExecutionStatus.SUCCESS with preserved verdict."""
    st, v = map_submodule_status(EvaluationStatus.SUCCESS, "BALANCED_GOVERNANCE")
    assert st == SubmoduleExecutionStatus.SUCCESS
    assert v == "BALANCED_GOVERNANCE"

    # Default verdict if omitted
    st_def, v_def = map_submodule_status(EvaluationStatus.SUCCESS, None)
    assert st_def == SubmoduleExecutionStatus.SUCCESS
    assert v_def == "OPTIMAL"


def test_status_mapping_data_absent():
    """EvaluationStatus.DATA_ABSENT -> SubmoduleExecutionStatus.BYPASSED with verdict 'DATA_ABSENT'."""
    st, v = map_submodule_status(EvaluationStatus.DATA_ABSENT, "ANY_VERDICT")
    assert st == SubmoduleExecutionStatus.BYPASSED
    assert v == "DATA_ABSENT"


def test_status_mapping_error():
    """EvaluationStatus.ERROR -> SubmoduleExecutionStatus.FAILED with preserved or 'ERROR' verdict."""
    st, v = map_submodule_status(EvaluationStatus.ERROR, "ZERO_DIVISION_IN_PARSER")
    assert st == SubmoduleExecutionStatus.FAILED
    assert v == "ZERO_DIVISION_IN_PARSER"

    st_def, v_def = map_submodule_status(EvaluationStatus.ERROR, None)
    assert st_def == SubmoduleExecutionStatus.FAILED
    assert v_def == "ERROR"


# =====================================================================
# 4. FULL SYNTHETIC ML RESULT TO API RESPONSE CONVERSION
# =====================================================================

def _create_synthetic_ml_pipeline_result() -> UnderwritingPipelineResult:
    """Helper to generate a fully populated, realistic UnderwritingPipelineResult."""
    # 18 synthetic feature values
    fv_values = [
        65.0, 45.0,  # OS
        92.0, 80.0,  # WPR
        71.5,        # MSR
        48.0, 52.0,  # CD
        84.0, 76.0,  # SD
        82.5, 75.0,  # ICR
        88.0, 62.0,  # CFS
        70.0, 64.0,  # RQ
        90.0, 85.0, 72.0,  # ICDL
    ]

    sub_results = {
        "OS": SubmoduleResult(
            submodule_code="OS",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.08,
            verdict="BALANCED_GOVERNANCE",
            indices={"Ownership_Dispersion_Index": 65.0, "Governance_Independence_Index": 45.0},
            summary="HHI 2500, Management Equity 40%, 1 independent director.",
            diagnostic_report="[SUBMODULE 4.1: OWNERSHIP STRUCTURE]\nVERDICT: BALANCED_GOVERNANCE",
        ),
        "WPR": SubmoduleResult(
            submodule_code="WPR",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.12,
            verdict="CLEAN_REPUTATION",
            indices={"Legal_Cleanliness_Index": 92.0, "Public_Reputation_Index": 80.0},
            summary="Zero tax claims, positive public sentiment.",
            diagnostic_report="[SUBMODULE 4.2: WEB REPUTATION]\nVERDICT: CLEAN_REPUTATION",
        ),
        "MSR": SubmoduleResult(
            submodule_code="MSR",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.05,
            verdict="MODERATE_EXPANSION",
            indices={"Sector_Vitality_Index": 71.5},
            summary="Sector IT Services expanding at 8.5% YoY.",
            diagnostic_report="[SUBMODULE 4.3: MACRO SECTOR]\nVERDICT: MODERATE_EXPANSION",
        ),
        "CD": SubmoduleResult(
            submodule_code="CD",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.10,
            verdict="ACCEPTABLE_DIVERSIFICATION",
            indices={"Client_Diversification_Index": 48.0, "Top_Client_Exposure_Index": 52.0},
            summary="Top client accounts for 28% of total revenue.",
            diagnostic_report="[SUBMODULE 4.4: CLIENT DEPENDENCY]\nVERDICT: ACCEPTABLE_DIVERSIFICATION",
        ),
        "SD": SubmoduleResult(
            submodule_code="SD",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.08,
            verdict="RESILIENT_SUPPLY_CHAIN",
            indices={"Supplier_Diversification_Index": 84.0, "Supply_Chain_Robustness_Index": 76.0},
            summary="Multi-vendor supplier network with local alternates.",
            diagnostic_report="[SUBMODULE 4.5: SUPPLIER DEPENDENCY]\nVERDICT: RESILIENT_SUPPLY_CHAIN",
        ),
        "ICR": SubmoduleResult(
            submodule_code="ICR",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.15,
            verdict="SOLVENT_CASH_BUFFER",
            indices={"Cash_Readiness_Index": 82.5, "Runway_Buffer_Index": 75.0},
            summary="3.2 months of operational runway preserved.",
            diagnostic_report="[SUBMODULE 4.6: CASH READINESS]\nVERDICT: SOLVENT_CASH_BUFFER",
        ),
        "CFS": SubmoduleResult(
            submodule_code="CFS",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.08,
            verdict="PREDICTABLE_REVENUE",
            indices={"Revenue_Predictability_Index": 88.0, "Revenue_Trajectory_Index": 62.0},
            summary="Coefficient of variation 0.14 on monthly cash inflows.",
            diagnostic_report="[SUBMODULE 4.7: CASHFLOW STABILITY]\nVERDICT: PREDICTABLE_REVENUE",
        ),
        "RQ": SubmoduleResult(
            submodule_code="RQ",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.14,
            verdict="LOW_AGING_RISK",
            indices={"Receivables_Safety_Index": 70.0, "Client_Payment_Discipline_Index": 64.0},
            summary="Days Sales Outstanding (DSO) at 42 days.",
            diagnostic_report="[SUBMODULE 4.8: RECEIVABLES QUALITY]\nVERDICT: LOW_AGING_RISK",
        ),
        "ICDL": SubmoduleResult(
            submodule_code="ICDL",
            status=EvaluationStatus.SUCCESS,
            impact_weight=0.16,
            verdict="LOW_LEVERAGE_PRIME",
            indices={
                "Debt_Repayment_Discipline_Index": 90.0,
                "Debt_Service_Coverage_Index": 85.0,
                "Solvency_Leverage_Index": 72.0,
            },
            summary="DSCR is 2.4x with zero historic debt defaults.",
            diagnostic_report="[SUBMODULE 4.9: CREDIT DISCIPLINE]\nVERDICT: LOW_LEVERAGE_PRIME",
        ),
    }

    scoring = CreditScoringResult(
        investment_attractiveness_score=78.64,
        probability_of_default=0.0832,
        verdict_category="PRIME_LOW_RISK",
        recommendation="APPROVED",
        shap_attributions={"OS": -0.8, "ICR": +3.2, "ICDL": +4.1},
        executive_summary="Enterprise evaluated with an overall Investment Attractiveness Score of 78.6/100.0 (PRIME_LOW_RISK).",
        llm_synthesis_prompt="[Synthesized underwriting prompt]",
    )

    return UnderwritingPipelineResult(
        business_id=uuid4(),
        as_of_date=date(2026, 9, 20),
        feature_vector=fv_values,
        submodule_results=sub_results,
        compiled_dossier_text="Compiled Underwriting Dossier text",
        scoring_result=scoring,
    )


def test_full_synthetic_ml_result_to_api_response():
    """Tests comprehensive conversion from UnderwritingPipelineResult to AnalysisReportResponse."""
    pipeline_res = _create_synthetic_ml_pipeline_result()
    test_run_id = uuid4()

    report: AnalysisReportResponse = map_ml_result_to_analysis_report(
        pipeline_result=pipeline_res,
        run_id=test_run_id,
        company_name="Acme Technology SRL",
        tax_id="1007600000001",
        sector_code="6201",
        max_credit_limit_mdl=Decimal("2500000.00"),
    )

    # 1. Identity and Run Metadata
    assert report.run_id == test_run_id
    assert report.company_name == "Acme Technology SRL"
    assert report.tax_id == "1007600000001"
    assert report.sector_code == "6201"
    assert report.status == AnalysisStatus.COMPLETED
    assert report.max_credit_limit_mdl == Decimal("2500000.00")

    # 2. Score & PD passed verbatim from ML core (never recalculated)
    assert report.universal_score == 78.64
    assert report.probability_of_default == 0.0832
    assert report.verdict_category == VerdictCategory.PRIME_LOW_RISK
    assert report.recommendation == Recommendation.APPROVED
    assert report.llm_final_summary == pipeline_res.scoring_result.executive_summary

    # 3. Feature Vector Object (18 named snake_case keys)
    fv = report.feature_vector
    fv_dict = fv.model_dump()
    assert len(fv_dict) == 18
    for expected_key in CANONICAL_18D_KEYS:
        assert expected_key in fv_dict
        assert fv_dict[expected_key] is not None

    # Exact matching of feature vector values
    assert fv.ownership_dispersion_index == 65.0
    assert fv.governance_independence_index == 45.0
    assert fv.legal_cleanliness_index == 92.0
    assert fv.public_reputation_index == 80.0
    assert fv.sector_vitality_index == 71.5
    assert fv.solvency_leverage_index == 72.0

    # 4. Feature Vector Ordered (Exact 18 elements in sequence)
    assert len(report.feature_vector_ordered) == 18
    assert report.feature_vector_ordered == pipeline_res.feature_vector

    # 5. Submodule Report Cards (All 9 in canonical sequence)
    assert len(report.submodules) == 9
    expected_ids = [pair[1] for pair in EXPECTED_SUBMODULE_PAIRS]
    actual_ids = [card.submodule_id for card in report.submodules]
    assert actual_ids == expected_ids

    # Check first card (OS_4_1)
    os_card = report.submodules[0]
    assert os_card.submodule_id == "OS_4_1"
    assert os_card.name == "Ownership Structure & Corporate Governance"
    assert os_card.status == SubmoduleExecutionStatus.SUCCESS
    assert os_card.verdict == "BALANCED_GOVERNANCE"
    assert os_card.impact_weight == 0.08
    assert os_card.indices == {
        "ownership_dispersion_index": 65.0,
        "governance_independence_index": 45.0,
    }
    assert "[SUBMODULE 4.1: OWNERSHIP STRUCTURE]" in os_card.dry_report

    # 6. LLM Synthesis Object
    synthesis = report.llm_synthesis
    assert synthesis.headline.startswith("Enterprise evaluated with an overall")
    assert synthesis.summary_markdown == pipeline_res.scoring_result.executive_summary
    assert len(synthesis.positive_indicators) > 0


# =====================================================================
# 5. ERROR PATH CARD & DEGRADED PIPELINE HANDLING
# =====================================================================

def test_error_and_data_absent_submodules():
    """Verifies degraded status, error card, and bypassed card mapping."""
    pipeline_res = _create_synthetic_ml_pipeline_result()

    # Inject an ERROR submodule and a DATA_ABSENT submodule
    pipeline_res.submodule_results["CD"] = SubmoduleResult(
        submodule_code="CD",
        status=EvaluationStatus.ERROR,
        impact_weight=0.10,
        verdict="FILE_CORRUPTED",
        indices={"Client_Diversification_Index": None, "Top_Client_Exposure_Index": None},
        summary="Bank ledger parsing failed with encoding error.",
        diagnostic_report="[SUBMODULE 4.4: CLIENT DEPENDENCY]\nSTATUS: ERROR\nVERDICT: FILE_CORRUPTED",
    )
    pipeline_res.submodule_results["RQ"] = SubmoduleResult(
        submodule_code="RQ",
        status=EvaluationStatus.DATA_ABSENT,
        impact_weight=0.14,
        verdict="MISSING_INVOICES",
        indices={"Receivables_Safety_Index": None, "Client_Payment_Discipline_Index": None},
        summary="Invoices ledger not provided.",
        diagnostic_report="[SUBMODULE 4.8: RECEIVABLES QUALITY]\nSTATUS: BYPASSED",
    )

    report = map_ml_result_to_analysis_report(pipeline_result=pipeline_res)

    # Status must degrade to DEGRADED
    assert report.status == AnalysisStatus.DEGRADED

    # Find CD_4_4 card
    cd_card = next(c for c in report.submodules if c.submodule_id == "CD_4_4")
    assert cd_card.status == SubmoduleExecutionStatus.FAILED
    assert cd_card.verdict == "FILE_CORRUPTED"
    assert cd_card.dry_report.startswith("[SUBMODULE 4.4: CLIENT DEPENDENCY]")

    # Find RQ_4_8 card
    rq_card = next(c for c in report.submodules if c.submodule_id == "RQ_4_8")
    assert rq_card.status == SubmoduleExecutionStatus.BYPASSED
    assert rq_card.verdict == "DATA_ABSENT"

    # Verify critical flags in synthesis reflect the error and absence
    flags = report.llm_synthesis.critical_flags
    assert any("[CD_4_4]" in f and "Execution error" in f for f in flags)
    assert any("[RQ_4_8]" in f and "Data absent" in f for f in flags)
