"""
Submodule 4.1: Ownership Structure Evaluator (OS).
Calculates shareholder concentration (HHI), management-ownership overlap, and governance independence.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from fintech_app.shared.schemas.user_types import EvaluationStatus


@dataclass
class SubmoduleResult:
    submodule_code: str
    status: EvaluationStatus
    impact_weight: float
    verdict: str
    indices: Dict[str, Optional[float]]
    summary: str
    diagnostic_report: str


class OwnershipStructureEvaluator:
    """Evaluates ownership dispersion and governance independence."""

    def __init__(self) -> None:
        self.code = "OS"
        self.impact_weight = 0.08

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        shareholders = getattr(snapshot, "shareholders", []) if snapshot else []
        business = getattr(snapshot, "business", None) if snapshot else None

        if not shareholders:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Ownership_Dispersion_Index": None,
                    "Governance_Independence_Index": None,
                },
                summary="No shareholder records present.",
                diagnostic_report=f"[SUBMODULE 4.1: OWNERSHIP STRUCTURE]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        # 1. Shareholder Concentration HHI
        hhi = sum((float(s.equity_percentage) ** 2) for s in shareholders)
        
        # 2. Management Overlap Ratio
        moor = sum(
            (float(s.equity_percentage) / 100.0)
            for s in shareholders
            if getattr(s, "is_management_member", False)
        )

        # 3. Governance Independence Ratio
        total_seats = getattr(business, "total_board_seats", 1) if business else 1
        ind_seats = getattr(business, "independent_directors_count", 0) if business else 0
        gir = ind_seats / max(total_seats, 1)

        dispersion_idx = max(0.0, min(100.0, 100.0 - (hhi / 100.0)))
        governance_idx = max(0.0, min(100.0, (gir * 70.0) + ((1.0 - moor) * 30.0)))

        verdict = "BALANCED_GOVERNANCE" if dispersion_idx >= 60 else "CONCENTRATED_OWNERSHIP"

        report = (
            f"[SUBMODULE 4.1: OWNERSHIP STRUCTURE]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Ownership Dispersion Index: {dispersion_idx:.1f} / 100.0\n"
            f"- Governance Independence Index: {governance_idx:.1f} / 100.0\n"
            f"SUMMARY: HHI calculated at {hhi:.1f}. Management holds {moor * 100:.1f}% equity. "
            f"Independent directors occupy {ind_seats} of {total_seats} seats."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Ownership_Dispersion_Index": dispersion_idx,
                "Governance_Independence_Index": governance_idx,
            },
            summary=f"HHI: {hhi:.1f}, Management Equity: {moor * 100:.1f}%.",
            diagnostic_report=report,
        )
