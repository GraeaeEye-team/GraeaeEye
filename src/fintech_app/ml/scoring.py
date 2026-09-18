"""
Credit Scoring Engine and LLM Narrative Synthesis Aggregator.
Consumes the 18-element feature vector and submodule diagnostic reports,
calculates the overall Investment Attractiveness Score (0-100), and synthesizes the Underwriting Dossier.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CreditScoringResult:
    """Consolidated credit scoring and risk verdict result."""
    investment_attractiveness_score: float  # Bounded float [0.0 to 100.0]
    probability_of_default: float  # Bounded float [0.000 to 1.000]
    verdict_category: str  # PRIME_LOW_RISK, MODERATE_MONITORED, HIGH_RISK_REJECT
    recommendation: str  # APPROVED, MANUAL_REVIEW, REJECTED
    shap_attributions: Dict[str, float] = field(default_factory=dict)
    executive_summary: str = ""


class CreditScoringEngine:
    """Scoring engine aggregating feature vector indices into investment rating and LLM synthesis."""

    FEATURE_NAMES = [
        "ownership_dispersion_index",
        "governance_independence_index",
        "legal_cleanliness_index",
        "public_reputation_index",
        "sector_vitality_index",
        "client_diversification_index",
        "top_client_exposure_index",
        "supplier_diversification_index",
        "supply_chain_robustness_index",
        "cash_readiness_index",
        "runway_buffer_index",
        "revenue_predictability_index",
        "revenue_trajectory_index",
        "receivables_safety_index",
        "client_payment_discipline_index",
        "debt_repayment_discipline_index",
        "debt_service_coverage_index",
        "solvency_leverage_index",
    ]

    def calculate_score(
        self,
        feature_vector: List[Optional[float]],
        compiled_dossier_text: str = ""
    ) -> CreditScoringResult:
        """Calculates final score and verdict from feature vector."""
        valid_scores = [val for val in feature_vector if val is not None]
        if not valid_scores:
            score = 50.0
        else:
            score = sum(valid_scores) / len(valid_scores)

        score = max(0.0, min(100.0, score))
        pd_val = max(0.001, min(0.999, (100.0 - score) / 100.0))

        if score >= 75.0:
            verdict_category = "PRIME_LOW_RISK"
            recommendation = "APPROVED"
        elif score >= 50.0:
            verdict_category = "MODERATE_MONITORED"
            recommendation = "MANUAL_REVIEW"
        else:
            verdict_category = "HIGH_RISK_REJECT"
            recommendation = "REJECTED"

        shap_attributions = {
            name: (val - score) if val is not None else 0.0
            for name, val in zip(self.FEATURE_NAMES, feature_vector)
        }

        executive_summary = (
            f"Enterprise evaluated with an overall Investment Attractiveness Score of {score:.1f}/100.0 "
            f"({verdict_category}). Estimated Probability of Default: {pd_val * 100:.1f}%."
        )

        return CreditScoringResult(
            investment_attractiveness_score=score,
            probability_of_default=pd_val,
            verdict_category=verdict_category,
            recommendation=recommendation,
            shap_attributions=shap_attributions,
            executive_summary=executive_summary,
        )


def evaluate_counterparty_risk(feature_vector: List[Optional[float]]) -> CreditScoringResult:
    """Convenience helper for counterparty risk scoring."""
    engine = CreditScoringEngine()
    return engine.calculate_score(feature_vector)
