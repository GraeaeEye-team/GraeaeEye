"""
Contract Mapping Layer: ML Core to API Gateway.

Provides pure mapping functions and schema conversions between the Underwriting
Analytical ML Core and FastAPI API schemas (Spec v2.0).

Invariants:
- Single source of truth: ML core definitions.
- Index keys: ML Title_Snake_Case -> API lowercase_snake_case via .lower()
- Submodule IDs: ML short (OS..ICDL) <-> API long (OS_4_1..ICDL_4_9)
- Statuses: ML EvaluationStatus -> API SubmoduleExecutionStatus + verdict
- Scores: universal_score and probability_of_default are passed verbatim from ML.
- Pure functions only: zero I/O, zero network, zero DB calls, zero async sleep.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from .schemas import (
    CANONICAL_18D_KEYS,
    AnalysisReportResponse,
    AnalysisStatus,
    FeatureVector,
    LLMSynthesisSummary,
    Recommendation,
    SubmoduleExecutionStatus,
    SubmoduleReportCard,
    VerdictCategory,
)
from ..ml.base import EvaluationStatus, SubmoduleResult
from ..ml.pipeline import UnderwritingPipelineResult
from ..ml.scoring import CreditScoringEngine, CreditScoringResult


# =====================================================================
# 1. SUBMODULE IDENTIFIER MAPPINGS (ML short <-> API long)
# =====================================================================

ML_TO_API_SUBMODULE_MAP: Dict[str, str] = {
    "OS": "OS_4_1",
    "WPR": "WPR_4_2",
    "MSR": "MSR_4_3",
    "CD": "CD_4_4",
    "SD": "SD_4_5",
    "ICR": "ICR_4_6",
    "CFS": "CFS_4_7",
    "RQ": "RQ_4_8",
    "ICDL": "ICDL_4_9",
}

API_TO_ML_SUBMODULE_MAP: Dict[str, str] = {v: k for k, v in ML_TO_API_SUBMODULE_MAP.items()}

SUBMODULE_NAMES: Dict[str, str] = {
    "OS": "Ownership Structure & Corporate Governance",
    "WPR": "Web Presence & Reputational Intelligence",
    "MSR": "Macroeconomic & Sector Risk",
    "CD": "Client Concentration & Dependency",
    "SD": "Supplier Concentration & Supply Chain",
    "ICR": "Immediate Cash Readiness",
    "CFS": "Cashflow Stability & Volatility",
    "RQ": "Receivables Quality & Counterparty Risk",
    "ICDL": "Credit Discipline & Leverage",
}


def ml_submodule_to_api(code: str) -> str:
    """Maps ML short submodule code ('OS') to API canonical long id ('OS_4_1')."""
    if code not in ML_TO_API_SUBMODULE_MAP:
        raise KeyError(f"Unknown ML submodule code: '{code}'. Expected one of {list(ML_TO_API_SUBMODULE_MAP.keys())}")
    return ML_TO_API_SUBMODULE_MAP[code]


def api_submodule_to_ml(long_id: str) -> str:
    """Maps API canonical long submodule id ('OS_4_1') to ML short code ('OS')."""
    if long_id not in API_TO_ML_SUBMODULE_MAP:
        raise KeyError(f"Unknown API submodule id: '{long_id}'. Expected one of {list(API_TO_ML_SUBMODULE_MAP.keys())}")
    return API_TO_ML_SUBMODULE_MAP[long_id]


# =====================================================================
# 2. 18D FEATURE VECTOR KEY MAPPINGS & BIJECTION ASSERTION
# =====================================================================


def _build_and_validate_index_mappings() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Constructs and rigorously validates the bidirectional 18D index key mapping.
    Fails loudly on any mismatch in count, casing, bijection, or ordering.
    """
    ml_names = CreditScoringEngine.FEATURE_NAMES
    api_keys = CANONICAL_18D_KEYS

    if len(ml_names) != 18:
        raise ValueError(f"ML CreditScoringEngine.FEATURE_NAMES must have exactly 18 items, got {len(ml_names)}")
    if len(api_keys) != 18:
        raise ValueError(f"API CANONICAL_18D_KEYS must have exactly 18 items, got {len(api_keys)}")

    ml_to_api: Dict[str, str] = {}
    api_to_ml: Dict[str, str] = {}

    for idx, (ml_feat, api_key) in enumerate(zip(ml_names, api_keys)):
        lower_ml = ml_feat.lower()
        if lower_ml != api_key:
            raise ValueError(
                f"Feature vector ordering/bijection mismatch at index {idx:02d}: "
                f"ML '{ml_feat}' (.lower()='{lower_ml}') != API '{api_key}'"
            )
        ml_to_api[ml_feat] = api_key
        api_to_ml[api_key] = ml_feat

    if len(ml_to_api) != 18 or len(api_to_ml) != 18:
        raise ValueError("Non-bijective index key mapping detected.")

    return ml_to_api, api_to_ml


ML_TO_API_INDEX_MAP, API_TO_ML_INDEX_MAP = _build_and_validate_index_mappings()

# Bijective mapping aliases for external contract verifications
FEATURE_KEY_ML_TO_API: Dict[str, str] = ML_TO_API_INDEX_MAP
FEATURE_KEY_API_TO_ML: Dict[str, str] = API_TO_ML_INDEX_MAP
SUBMODULE_CODE_ML_TO_API: Dict[str, str] = ML_TO_API_SUBMODULE_MAP
SUBMODULE_CODE_API_TO_ML: Dict[str, str] = API_TO_ML_SUBMODULE_MAP


def ml_index_to_api(ml_key: str) -> str:
    """Converts ML Title_Snake_Case index key to API snake_case."""
    mapped = ML_TO_API_INDEX_MAP.get(ml_key)
    if mapped is not None:
        return mapped
    # Fallback to pure lowercasing if already valid
    lower = ml_key.lower()
    if lower in API_TO_ML_INDEX_MAP:
        return lower
    raise KeyError(f"Unknown ML index key: '{ml_key}'")


def api_index_to_ml(api_key: str) -> str:
    """Converts API snake_case index key to ML Title_Snake_Case."""
    mapped = API_TO_ML_INDEX_MAP.get(api_key)
    if mapped is not None:
        return mapped
    raise KeyError(f"Unknown API index key: '{api_key}'")


# =====================================================================
# 3. STATUS & VERDICT MAPPING
# =====================================================================


def map_submodule_status(
    status: EvaluationStatus,
    ml_verdict: Optional[str] = None,
) -> Tuple[SubmoduleExecutionStatus, str]:
    """
    Translates ML EvaluationStatus and verdict into API SubmoduleExecutionStatus and verdict.

    Rules:
    - EvaluationStatus.SUCCESS -> API SUCCESS + preserved ML verdict (default 'OPTIMAL')
    - EvaluationStatus.DATA_ABSENT -> API BYPASSED + verdict 'DATA_ABSENT'
    - EvaluationStatus.ERROR -> API FAILED + preserved ML verdict or 'ERROR'
    """
    if status == EvaluationStatus.SUCCESS:
        verdict = ml_verdict.strip() if ml_verdict and ml_verdict.strip() else "OPTIMAL"
        return SubmoduleExecutionStatus.SUCCESS, verdict
    elif status == EvaluationStatus.DATA_ABSENT:
        return SubmoduleExecutionStatus.BYPASSED, "DATA_ABSENT"
    elif status == EvaluationStatus.ERROR:
        verdict = ml_verdict.strip() if ml_verdict and ml_verdict.strip() else "ERROR"
        return SubmoduleExecutionStatus.FAILED, verdict
    else:
        raise ValueError(f"Unrecognized EvaluationStatus: '{status}'")


# =====================================================================
# 4. DETERMINISTIC LLM SYNTHESIS BUILDER
# =====================================================================


def build_llm_synthesis(
    scoring_result: Optional[CreditScoringResult],
    submodule_results: Dict[str, SubmoduleResult],
) -> LLMSynthesisSummary:
    """
    Deterministically constructs the LLMSynthesisSummary from ML scoring and dry reports.
    Extracts high-impact critical flags and positive indicators from submodule results.
    """
    critical_flags: List[str] = []
    positive_indicators: List[str] = []

    # 1. Headline
    if scoring_result and scoring_result.executive_summary:
        first_sentence = scoring_result.executive_summary.split(".")[0].strip()
        headline = f"{first_sentence}." if not first_sentence.endswith(".") else first_sentence
    elif scoring_result:
        headline = (
            f"Underwriting evaluation: {scoring_result.verdict_category} "
            f"({scoring_result.recommendation}) at score {scoring_result.universal_score:.1f}/100.0."
        )
    else:
        headline = "Credit Underwriting Analysis Assessment."

    # 2. Summary Markdown
    if scoring_result and scoring_result.executive_summary:
        summary_markdown = scoring_result.executive_summary
    else:
        summary_markdown = "Underwriting evaluation completed with compiled submodule dossiers."

    # 3. Flags and Indicators from Submodules
    for code in CreditScoringEngine.SUBMODULE_WEIGHTS:
        res = submodule_results.get(code)
        if not res:
            continue

        long_id = ML_TO_API_SUBMODULE_MAP.get(code, code)

        if res.status == EvaluationStatus.ERROR:
            err_msg = res.summary or res.verdict or "Submodule calculation failed"
            critical_flags.append(f"[{long_id}] Execution error encountered: {err_msg}")
        elif res.status == EvaluationStatus.DATA_ABSENT:
            critical_flags.append(f"[{long_id}] Data absent: execution bypassed due to missing financial ledgers.")
        elif res.status == EvaluationStatus.SUCCESS:
            # Check numerical indices for risk vulnerabilities (< 40.0) or strengths (>= 70.0)
            if res.indices:
                for ml_idx_name, idx_val in res.indices.items():
                    if idx_val is not None:
                        snake_idx = ml_idx_name.lower()
                        if idx_val < 40.0:
                            critical_flags.append(f"[{long_id}] Weak metric '{snake_idx}': {idx_val:.1f}/100.0.")
                        elif idx_val >= 70.0:
                            positive_indicators.append(f"[{long_id}] Robust metric '{snake_idx}': {idx_val:.1f}/100.0.")

    # 4. Top-level risk flags from scoring
    if scoring_result:
        if scoring_result.probability_of_default >= 0.25:
            critical_flags.append(
                f"Elevated default risk: Estimated Probability of Default (PD) is "
                f"{scoring_result.probability_of_default * 100.0:.2f}%."
            )
        elif scoring_result.probability_of_default <= 0.05:
            positive_indicators.append(
                f"Minimal default risk: Estimated Probability of Default (PD) is "
                f"{scoring_result.probability_of_default * 100.0:.2f}%."
            )

    return LLMSynthesisSummary(
        headline=headline,
        summary_markdown=summary_markdown,
        critical_flags=critical_flags,
        positive_indicators=positive_indicators,
    )


# =====================================================================
# 5. FULL RESULT MAPPING
# =====================================================================


def map_ml_result_to_analysis_report(
    pipeline_result: UnderwritingPipelineResult,
    run_id: Optional[UUID] = None,
    company_name: str = "Evaluated Enterprise",
    tax_id: str = "0000000000000",
    sector_code: str = "0000",
    created_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    max_credit_limit_mdl: Decimal = Decimal("1250000.00"),
) -> AnalysisReportResponse:
    """
    Converts UnderwritingPipelineResult and CreditScoringResult into a complete
    AnalysisReportResponse strictly adhering to Spec v2.0 §5.4.

    Key guarantees:
    - universal_score and probability_of_default taken FROM ML verbatim (never recalculated).
    - feature_vector object has 18 named snake_case keys.
    - feature_vector_ordered contains the exact 18 values in canonical sequence.
    - Submodule report cards preserve ML diagnostic report text and impact weights.
    """
    scoring = pipeline_result.scoring_result

    # 1. Scores (Verbatim from ML)
    if scoring is not None:
        universal_score = float(scoring.universal_score)
        probability_of_default = float(scoring.probability_of_default)
        try:
            verdict_cat = VerdictCategory(scoring.verdict_category)
        except ValueError:
            verdict_cat = VerdictCategory.MODERATE_MONITORED
        try:
            rec = Recommendation(scoring.recommendation)
        except ValueError:
            rec = Recommendation.MANUAL_REVIEW
        llm_final_summary = scoring.executive_summary
    else:
        universal_score = 50.0
        probability_of_default = 0.5000
        verdict_cat = VerdictCategory.MODERATE_MONITORED
        rec = Recommendation.MANUAL_REVIEW
        llm_final_summary = pipeline_result.compiled_dossier_text or "Analysis completed without scoring summary."

    # 2. Feature Vector (Object & Ordered List)
    ordered_fv = list(pipeline_result.feature_vector)
    if len(ordered_fv) != 18:
        raise ValueError(
            f"UnderwritingPipelineResult.feature_vector must contain exactly 18 items, got {len(ordered_fv)}"
        )

    fv_dict: Dict[str, Optional[float]] = {}
    for api_key, val in zip(CANONICAL_18D_KEYS, ordered_fv):
        fv_dict[api_key] = float(val) if val is not None else None

    feature_vector_obj = FeatureVector(**fv_dict)

    # 3. Submodule Report Cards (All 9 in canonical order)
    submodule_cards: List[SubmoduleReportCard] = []
    for code, base_weight in CreditScoringEngine.SUBMODULE_WEIGHTS.items():
        long_id = ML_TO_API_SUBMODULE_MAP[code]
        name = SUBMODULE_NAMES.get(code, f"Submodule {long_id}")
        res = pipeline_result.submodule_results.get(code)

        if res is not None:
            api_status, api_verdict = map_submodule_status(res.status, res.verdict)
            card_indices: Optional[Dict[str, Optional[float]]] = None
            if res.indices:
                card_indices = {}
                for ik, iv in res.indices.items():
                    snake_k = ml_index_to_api(ik)
                    card_indices[snake_k] = float(iv) if iv is not None else None
            dry_report = res.diagnostic_report or res.summary or f"[Report for {long_id}]"
            weight = float(res.impact_weight) if res.impact_weight is not None else base_weight
        else:
            api_status = SubmoduleExecutionStatus.BYPASSED
            api_verdict = "DATA_ABSENT"
            card_indices = None
            dry_report = f"[SUBMODULE {long_id}]\nSTATUS: BYPASSED\nVERDICT: DATA_ABSENT"
            weight = base_weight

        card = SubmoduleReportCard(
            submodule_id=long_id,
            name=name,
            status=api_status,
            verdict=api_verdict,
            impact_weight=weight,
            indices=card_indices,
            dry_report=dry_report,
        )
        submodule_cards.append(card)

    # 4. Overall Pipeline Status
    has_error = any(res.status == EvaluationStatus.ERROR for res in pipeline_result.submodule_results.values())
    has_bypassed = any(res.status == EvaluationStatus.DATA_ABSENT for res in pipeline_result.submodule_results.values())

    if has_error:
        overall_status = AnalysisStatus.DEGRADED
    elif has_bypassed:
        overall_status = AnalysisStatus.DEGRADED
    else:
        overall_status = AnalysisStatus.COMPLETED

    # 5. Deterministic LLM Synthesis
    llm_synthesis = build_llm_synthesis(scoring, pipeline_result.submodule_results)

    now = datetime.now(timezone.utc)

    return AnalysisReportResponse(
        run_id=run_id or uuid4(),
        company_name=company_name,
        tax_id=tax_id,
        sector_code=sector_code,
        status=overall_status,
        execution_status="COMPLETED",
        created_at=created_at or now,
        completed_at=completed_at or now,
        feature_vector=feature_vector_obj,
        feature_vector_ordered=ordered_fv,
        submodules=submodule_cards,
        universal_score=universal_score,
        probability_of_default=probability_of_default,
        verdict_category=verdict_cat,
        recommendation=rec,
        llm_synthesis=llm_synthesis,
        llm_final_summary=llm_final_summary,
        max_credit_limit_mdl=max_credit_limit_mdl,
    )


__all__ = [
    "ML_TO_API_SUBMODULE_MAP",
    "API_TO_ML_SUBMODULE_MAP",
    "SUBMODULE_CODE_ML_TO_API",
    "SUBMODULE_CODE_API_TO_ML",
    "SUBMODULE_NAMES",
    "ML_TO_API_INDEX_MAP",
    "API_TO_ML_INDEX_MAP",
    "FEATURE_KEY_ML_TO_API",
    "FEATURE_KEY_API_TO_ML",
    "ml_submodule_to_api",
    "api_submodule_to_ml",
    "ml_index_to_api",
    "api_index_to_ml",
    "map_submodule_status",
    "build_llm_synthesis",
    "map_ml_result_to_analysis_report",
]
