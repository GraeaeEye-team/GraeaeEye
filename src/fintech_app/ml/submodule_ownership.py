"""
Submodule 4.1: Ownership Structure Evaluator (OS).
Calculates shareholder concentration (HHI), management-ownership overlap (MOOR),
governance independence (GIR), and evaluates capital stability and key-person risk.
"""
from typing import Any

from .base import (
    BaseSubmoduleEvaluator,
    SubmoduleResult,
    clamp,
    safe_div,
)
from ..shared.schemas.user_types import EvaluationStatus


class OwnershipStructureEvaluator(BaseSubmoduleEvaluator):
    """Evaluates ownership dispersion, governance independence, and key-person risk."""

    submodule_code: str = "OS"
    impact_weight: float = 0.08

    def __init__(self) -> None:
        super().__init__(submodule_code="OS", impact_weight=0.08)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        shareholders = getattr(snapshot, "shareholders", None) if snapshot else None
        business = getattr(snapshot, "business", None) if snapshot else None

        if not shareholders:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Ownership_Dispersion_Index": None,
                    "Governance_Independence_Index": None,
                },
                summary="No shareholder records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.1: OWNERSHIP STRUCTURE]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        # 1. Shareholder Concentration (Herfindahl-Hirschman Index - HHI_Shareholders)
        # HHI = Sum( (equity_percentage_i)^2 )
        hhi = sum((float(getattr(s, "equity_percentage", 0.0)) ** 2) for s in shareholders)

        # 2. Management-Ownership Overlap Ratio (MOOR)
        mgmt_equity = sum(
            float(getattr(s, "equity_percentage", 0.0))
            for s in shareholders
            if getattr(s, "is_management_member", False)
        )
        moor = safe_div(mgmt_equity, 100.0, default_denom=1.0)

        # 3. Governance Independence Ratio (GIR)
        total_seats = int(getattr(business, "total_board_seats", 1)) if business else 1
        ind_seats = int(getattr(business, "independent_directors_count", 0)) if business else 0
        gir = safe_div(ind_seats, max(total_seats, 1), default_denom=1.0)

        # 4. Normalized Output Indices
        dispersion_idx = clamp(100.0 - (hhi / 100.0))
        governance_idx = clamp((gir * 70.0) + ((1.0 - moor) * 30.0))

        # 5. Verdict determination
        if moor >= 0.5:
            verdict = "KEY_PERSON_RISK"
        elif dispersion_idx >= 60.0:
            verdict = "BALANCED_GOVERNANCE"
        else:
            verdict = "CONCENTRATED_OWNERSHIP"

        report = (
            f"[SUBMODULE 4.1: OWNERSHIP STRUCTURE]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Ownership Dispersion Index: {dispersion_idx:.1f} / 100.0\n"
            f"- Governance Independence Index: {governance_idx:.1f} / 100.0\n"
            f"SUMMARY: HHI_Shareholders calculated at {hhi:.1f}. "
            f"Management holds {moor * 100.0:.1f}% of equity. "
            f"Independent directors occupy {ind_seats} of {total_seats} seats."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Ownership_Dispersion_Index": dispersion_idx,
                "Governance_Independence_Index": governance_idx,
            },
            summary=(
                f"HHI: {hhi:.1f}, Management Equity: {moor * 100.0:.1f}%, "
                f"Board Independence: {gir * 100.0:.1f}%."
            ),
            diagnostic_report=report,
        )


__all__ = [
    "OwnershipStructureEvaluator",
    "SubmoduleResult",
]
