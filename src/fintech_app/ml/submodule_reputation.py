"""
Submodule 4.2: Web Presence & Legal Reputation Evaluator (WPR).
Evaluates open lawsuits, claims amount against cash, sanctions check, and news sentiment.
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class WebReputationEvaluator:
    """Evaluates litigation exposure, sanctions, and reputational sentiment."""

    def __init__(self) -> None:
        self.code = "WPR"
        self.impact_weight = 0.12

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        web_rep = getattr(snapshot, "web_reputation", None) if snapshot else None
        bank_accounts = getattr(snapshot, "bank_accounts", []) if snapshot else []

        if not web_rep:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Legal_Cleanliness_Index": None,
                    "Public_Reputation_Index": None,
                },
                summary="No web reputation data present.",
                diagnostic_report="[SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        if getattr(web_rep, "is_in_sanctions_list", False):
            legal_idx = 0.0
        else:
            liquid_cash = sum(float(getattr(acc, "current_balance", 0.0)) for acc in bank_accounts)
            claims = float(getattr(web_rep, "total_lawsuit_claims_amount", 0.0))
            ler = claims / max(liquid_cash, 1.0)
            lawsuits_count = getattr(web_rep, "active_lawsuits_count", 0)
            base_legal = 100.0 - (lawsuits_count * 15.0) - min(50.0, ler * 50.0)
            legal_idx = max(0.0, min(100.0, base_legal))

        sentiment = getattr(web_rep, "news_sentiment_score", None)
        if sentiment is None:
            reputation_idx = 50.0
        else:
            reputation_idx = max(0.0, min(100.0, (float(sentiment) + 1.0) * 50.0))

        verdict = "LEGAL_INTEGRITY_CONFIRMED" if legal_idx >= 75.0 else "LITIGATION_EXPOSURE"

        report = (
            f"[SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Legal Cleanliness Index: {legal_idx:.1f} / 100.0\n"
            f"- Public Reputation Index: {reputation_idx:.1f} / 100.0\n"
            f"SUMMARY: Identified {getattr(web_rep, 'active_lawsuits_count', 0)} active lawsuits. "
            f"Sanctions check: {'FAIL' if getattr(web_rep, 'is_in_sanctions_list', False) else 'PASS'}. "
            f"News sentiment score: {sentiment}."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Legal_Cleanliness_Index": legal_idx,
                "Public_Reputation_Index": reputation_idx,
            },
            summary=f"Legal Cleanliness: {legal_idx:.1f}, Reputation: {reputation_idx:.1f}.",
            diagnostic_report=report,
        )

