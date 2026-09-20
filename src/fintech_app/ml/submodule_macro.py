"""
Submodule 4.3: Macro & Sector Risk Evaluator (MSR).
Evaluates industry YoY growth rate, baseline default rates, and macroeconomic risk outlook
to assess systemic sector-level risks.
"""
from typing import Any

from .base import (
    BaseSubmoduleEvaluator,
    SubmoduleResult,
    clamp,
)
from ..schemas.user_types import EvaluationStatus


class MacroSectorRiskEvaluator(BaseSubmoduleEvaluator):
    """Evaluates macroeconomic industry growth, sector default safety, and risk outlook."""

    submodule_code: str = "MSR"
    impact_weight: float = 0.05

    def __init__(self) -> None:
        super().__init__(submodule_code="MSR", impact_weight=0.05)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        macro = (
            getattr(snapshot, "macro_metrics", None)
            or getattr(snapshot, "macro_sector_metrics", None)
            if snapshot
            else None
        )
        business = getattr(snapshot, "business", None) if snapshot else None
        industry_code = str(getattr(business, "industry_code", "N/A")) if business else "N/A"

        if not macro:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Sector_Vitality_Index": None,
                },
                summary="No macro sector metrics data present.",
                diagnostic_report=(
                    "[SUBMODULE 4.3: MACRO & SECTOR RISK]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        growth_rate = float(getattr(macro, "sector_growth_rate_yoy", 0.0))
        default_rate = float(getattr(macro, "sector_default_rate", 0.0))
        outlook_score = float(getattr(macro, "risk_outlook_score", 5))

        # 1. Component calculations
        growth_score = clamp(50.0 + (growth_rate * 5.0))
        default_safety = clamp(100.0 - (default_rate * 5.0))
        macro_stability = clamp(100.0 - ((outlook_score - 1.0) * 11.11))

        # 2. Consolidated Sector Vitality Index
        vitality_idx = clamp(
            (0.40 * growth_score) + (0.35 * default_safety) + (0.25 * macro_stability)
        )

        # 3. Verdict determination
        if vitality_idx >= 70.0:
            verdict = "EXPANDING_SECTOR"
        elif vitality_idx >= 40.0:
            verdict = "STABLE_SECTOR"
        else:
            verdict = "HIGH_RISK_SECTOR"

        report = (
            f"[SUBMODULE 4.3: MACRO & SECTOR RISK]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Sector Vitality Index: {vitality_idx:.1f} / 100.0\n"
            f"SUMMARY: Industry code {industry_code} exhibits YoY growth of {growth_rate:.1f}% "
            f"and average default rate of {default_rate:.1f}%. "
            f"Macro sector threat index is rated {int(outlook_score)}/10."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Sector_Vitality_Index": vitality_idx,
            },
            summary=f"Sector Vitality: {vitality_idx:.1f}, Industry: {industry_code}.",
            diagnostic_report=report,
        )


__all__ = [
    "MacroSectorRiskEvaluator",
]
