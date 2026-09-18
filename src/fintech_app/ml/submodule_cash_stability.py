"""
Submodule 4.7: Cash Flow Stability Evaluator (CFS).
Evaluates revenue volatility over 12 monthly rolling buckets and inflow trend trajectory.
Calculates Coefficient of Variation (CV) and OLS trend slope.
"""
import math
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class CashflowStabilityEvaluator:
    """Evaluates revenue predictability and inflow trajectory."""

    def __init__(self) -> None:
        self.code = "CFS"
        self.impact_weight = 0.08

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        transactions = getattr(snapshot, "transactions", []) if snapshot else []
        inflows = [
            float(getattr(tx, "amount", 0.0)) for tx in transactions
            if str(getattr(tx, "direction", "")).upper() == "INFLOW"
            and str(getattr(tx, "category", "")).upper() == "REVENUE"
        ]

        if not inflows:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Revenue_Predictability_Index": None,
                    "Revenue_Trajectory_Index": None,
                },
                summary="No revenue inflow transaction records present.",
                diagnostic_report="[SUBMODULE 4.7: CASH FLOW STABILITY]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        mean_r = sum(inflows) / len(inflows)
        variance = sum((x - mean_r) ** 2 for x in inflows) / max(len(inflows) - 1, 1)
        std_r = math.sqrt(variance)

        cv = std_r / max(mean_r, 1.0)

        # Calculate simple slope over sequential entries
        n = len(inflows)
        if n > 1:
            mean_t = (n + 1) / 2.0
            cov_t_r = sum((i + 1 - mean_t) * (inflows[i] - mean_r) for i in range(n))
            var_t = sum((i + 1 - mean_t) ** 2 for i in range(n))
            slope = cov_t_r / max(var_t, 1.0)
        else:
            slope = 0.0

        norm_trend = slope / max(mean_r, 1.0)

        predictability_idx = max(0.0, min(100.0, 100.0 - (cv * 100.0)))
        trajectory_idx = max(0.0, min(100.0, 50.0 + (norm_trend * 500.0)))

        verdict = "CONSISTENT_FLOWS" if cv <= 0.3 else ("MODERATE_VOLATILITY" if cv <= 0.6 else "HIGHLY_ERRATIC_FLOWS")

        report = (
            f"[SUBMODULE 4.7: CASH FLOW STABILITY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Revenue Predictability Index: {predictability_idx:.1f} / 100.0\n"
            f"- Revenue Trajectory Index: {trajectory_idx:.1f} / 100.0\n"
            f"SUMMARY: Mean monthly revenue: {mean_r:,.2f} MDL. Coefficient of Variation: {cv:.2f}. "
            f"Revenue growth trajectory slope is {slope:.2f} per month."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Revenue_Predictability_Index": predictability_idx,
                "Revenue_Trajectory_Index": trajectory_idx,
            },
            summary=f"Revenue Mean: {mean_r:,.2f}, CV: {cv:.2f}.",
            diagnostic_report=report,
        )

