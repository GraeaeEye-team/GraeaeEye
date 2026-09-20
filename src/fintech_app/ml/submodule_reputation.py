"""
Submodule 4.2: Web Presence & Legal Reputation Evaluator (WPR).
Evaluates open lawsuits, claims amount against liquid cash, sanctions check,
and news sentiment to detect reputational and legal risks.
"""

from typing import Any

from .base import (
    BaseSubmoduleEvaluator,
    SubmoduleResult,
    clamp,
    safe_div,
)
from ..shared.schemas.user_types import EvaluationStatus


class WebReputationEvaluator(BaseSubmoduleEvaluator):
    """Evaluates litigation exposure, sanctions hit, and public sentiment."""

    submodule_code: str = "WPR"
    impact_weight: float = 0.12

    def __init__(self) -> None:
        super().__init__(submodule_code="WPR", impact_weight=0.12)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        web_rep = getattr(snapshot, "web_reputation", None) if snapshot else None
        bank_accounts = getattr(snapshot, "bank_accounts", []) if snapshot else []

        if not web_rep:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Legal_Cleanliness_Index": None,
                    "Public_Reputation_Index": None,
                },
                summary="No web reputation data present.",
                diagnostic_report=(
                    "[SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION]\n" "STATUS: DATA_ABSENT\n" "VERDICT: DATA_ABSENT"
                ),
            )

        is_in_sanctions = bool(getattr(web_rep, "is_in_sanctions_list", False))
        claims = float(getattr(web_rep, "total_lawsuit_claims_amount", 0.0))
        active_lawsuits = int(getattr(web_rep, "active_lawsuits_count", 0))

        # 1. Legal Cleanliness Calculation
        if is_in_sanctions:
            legal_idx = 0.0
        else:
            liquid_cash = sum(float(getattr(acc, "current_balance", 0.0)) for acc in bank_accounts)
            ler = safe_div(claims, max(liquid_cash, 1.0), default_denom=1.0)
            base_legal = 100.0 - (active_lawsuits * 15.0) - min(50.0, ler * 50.0)
            legal_idx = clamp(base_legal)

        # 2. Public Reputation Calculation
        sentiment = getattr(web_rep, "news_sentiment_score", None)
        if sentiment is None:
            reputation_idx = 50.0
            sentiment_str = "N/A"
        else:
            sentiment_val = float(sentiment)
            reputation_idx = clamp((sentiment_val + 1.0) * 50.0)
            sentiment_str = f"{sentiment_val:+.3f}"

        # 3. Verdict determination
        if is_in_sanctions or legal_idx < 50.0:
            verdict = "CRITICAL_LEGAL_FLAG"
        elif legal_idx >= 75.0:
            verdict = "LEGAL_INTEGRITY_CONFIRMED"
        else:
            verdict = "LITIGATION_EXPOSURE"

        sanctions_status = "FAIL" if is_in_sanctions else "PASS"

        report = (
            f"[SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Legal Cleanliness Index: {legal_idx:.1f} / 100.0\n"
            f"- Public Reputation Index: {reputation_idx:.1f} / 100.0\n"
            f"SUMMARY: Identified {active_lawsuits} active lawsuits totaling {claims:,.2f} MDL. "
            f"Sanctions check: {sanctions_status}. "
            f"News sentiment classified at {sentiment_str}."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Legal_Cleanliness_Index": legal_idx,
                "Public_Reputation_Index": reputation_idx,
            },
            summary=(
                f"Legal Cleanliness: {legal_idx:.1f}, Reputation: {reputation_idx:.1f}, "
                f"Sanctions: {sanctions_status}."
            ),
            diagnostic_report=report,
        )


__all__ = [
    "WebReputationEvaluator",
]
