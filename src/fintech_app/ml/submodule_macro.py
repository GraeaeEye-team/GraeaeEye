"""
Submodule 4.3: Macro & Sector Risk Evaluator (MSR).
Evaluates industry growth rate YoY, sector default rate, and threat outlook.
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class MacroSectorRiskEvaluator:
    """Evaluates macro industry growth, default baseline, and risk outlook."""

    def __init__(self) -> None:
        self.code = "MSR"
        self.impact_weight = 0.05

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        macro = getattr(snapshot, "macro_metrics", None) if snapshot else None
        business = getattr(snapshot, "business", None) if snapshot else None
        industry_code = getattr(business, "industry_code", "N/A") if business else "N/A"

        if not macro:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Sector_Vitality_Index": None,
                },
                summary="No macro sector metrics data present.",
                diagnostic_report="[SUBMODULE 4.3: MACRO & SECTOR RISK]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        growth_rate = float(getattr(macro, "sector_growth_rate_yoy", 0.0))
        default_rate = float(getattr(macro, "sector_default_rate", 0.0))
        outlook_score = int(getattr(macro, "risk_outlook_score", 5))

        growth_score = max(0.0, min(100.0, 50.0 + (growth_rate * 5.0)))
        default_score = max(0.0, min(100.0, 100.0 - (default_rate * 5.0)))
        stability_score = max(0.0, min(100.0, 100.0 - ((outlook_score - 1) * 11.11)))

        vitality_idx = (0.40 * growth_score) + (0.35 * default_score) + (0.25 * stability_score)

        verdict = "EXPANDING_SECTOR" if vitality_idx >= 70 else ("STABLE_SECTOR" if vitality_idx >= 40 else "HIGH_RISK_SECTOR")

        report = (
            f"[SUBMODULE 4.3: MACRO & SECTOR RISK]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Sector Vitality Index: {vitality_idx:.1f} / 100.0\n"
            f"SUMMARY: Industry code {industry_code} exhibits YoY growth of {growth_rate:.1f}% "
            f"and average default rate of {default_rate:.1f}%. Risk outlook: {outlook_score}/10."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Sector_Vitality_Index": vitality_idx,
            },
            summary=f"Sector Vitality: {vitality_idx:.1f}.",
            diagnostic_report=report,
        )

