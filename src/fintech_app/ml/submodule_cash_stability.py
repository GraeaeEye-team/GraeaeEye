"""
Submodule 4.7: Cash Flow Stability Evaluator (CFS).
Evaluates revenue volatility over 12 monthly rolling buckets and inflow trend trajectory.
Calculates Coefficient of Variation (CV) and OLS trend slope.
"""

from datetime import date, datetime
import math
from typing import Any

from .base import (
    BaseSubmoduleEvaluator,
    SubmoduleResult,
    clamp,
)
from ..shared.schemas.user_types import EvaluationStatus


class CashflowStabilityEvaluator(BaseSubmoduleEvaluator):
    """Evaluates revenue predictability, cash flow volatility, and inflow trajectory."""

    submodule_code: str = "CFS"
    impact_weight: float = 0.08

    def __init__(self) -> None:
        super().__init__(submodule_code="CFS", impact_weight=0.08)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        transactions = getattr(snapshot, "transactions", []) if snapshot else []

        # Filter incoming revenue transactions
        revenue_txs = [
            tx
            for tx in transactions
            if str(getattr(tx, "direction", "")).upper() == "INFLOW"
            and str(getattr(tx, "category", "")).upper() in ("CLIENT_REVENUE", "REVENUE")
        ]
        # Fallback to general INFLOW if no explicit CLIENT_REVENUE/REVENUE
        if not revenue_txs:
            revenue_txs = [tx for tx in transactions if str(getattr(tx, "direction", "")).upper() == "INFLOW"]

        if not revenue_txs:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Revenue_Predictability_Index": None,
                    "Revenue_Trajectory_Index": None,
                },
                summary="No revenue inflow transaction records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.7: CASH FLOW STABILITY]\n" "STATUS: DATA_ABSENT\n" "VERDICT: DATA_ABSENT"
                ),
            )

        # Determine reference date
        raw_as_of = getattr(snapshot, "as_of_date", None)
        if raw_as_of is None:
            as_of_date = date.today()
        elif isinstance(raw_as_of, datetime):
            as_of_date = raw_as_of.date()
        else:
            as_of_date = raw_as_of

        # Build 12 calendar month keys up to as_of_date: (year, month) from t=1 to t=12
        month_keys = []
        y, m = as_of_date.year, as_of_date.month
        for i in range(11, -1, -1):
            total_months = y * 12 + (m - 1) - i
            bucket_year = total_months // 12
            bucket_month = (total_months % 12) + 1
            month_keys.append((bucket_year, bucket_month))

        # Check if transactions carry date/timestamp metadata
        has_dates = any(
            getattr(tx, "timestamp", None) is not None or getattr(tx, "transaction_date", None) is not None
            for tx in revenue_txs
        )

        if has_dates:
            monthly_buckets = {k: 0.0 for k in month_keys}
            has_matching_inflows = False
            for tx in revenue_txs:
                dt = getattr(tx, "timestamp", None) or getattr(tx, "transaction_date", None)
                if dt is not None:
                    if isinstance(dt, datetime):
                        dt = dt.date()
                    key = (dt.year, dt.month)
                    if key in monthly_buckets:
                        monthly_buckets[key] += abs(float(getattr(tx, "amount", 0.0)))
                        has_matching_inflows = True

            if not has_matching_inflows:
                return SubmoduleResult(
                    submodule_code=self.submodule_code,
                    status=EvaluationStatus.DATA_ABSENT,
                    impact_weight=self.impact_weight,
                    verdict="DATA_ABSENT",
                    indices={
                        "Revenue_Predictability_Index": None,
                        "Revenue_Trajectory_Index": None,
                    },
                    summary="No revenue inflow records within trailing 12-month period.",
                    diagnostic_report=(
                        "[SUBMODULE 4.7: CASH FLOW STABILITY]\n" "STATUS: DATA_ABSENT\n" "VERDICT: DATA_ABSENT"
                    ),
                )

            r_values = [monthly_buckets[k] for k in month_keys]
        else:
            # Dateless transaction list (e.g. synthetic test fixtures)
            inflows = [abs(float(getattr(tx, "amount", 0.0))) for tx in revenue_txs]
            if len(inflows) == 12:
                r_values = inflows
            elif len(inflows) < 12:
                r_values = [0.0] * (12 - len(inflows)) + inflows
            else:
                r_values = inflows[-12:]

        # 1. Mean Monthly Revenue (Mean_R) across 12 monthly buckets
        mean_r = sum(r_values) / 12.0

        # 2. Sample Standard Deviation (Std_R, ddof=1)
        variance = sum((r - mean_r) ** 2 for r in r_values) / 11.0
        std_r = math.sqrt(variance)

        # 3. Coefficient of Variation (CV_Revenue)
        cv = std_r / max(mean_r, 1.0)

        # 4. Trend Slope via Ordinary Least Squares (OLS) over t = 1..12
        # Mean of t (1..12) is 6.5; Variance of t is sum((t - 6.5)^2) = 143.0
        mean_t = 6.5
        var_t = 143.0
        cov_t_r = sum((t - mean_t) * (r_values[t - 1] - mean_r) for t in range(1, 13))
        slope = cov_t_r / max(var_t, 1.0)

        # 5. Normalized Trend
        norm_trend = slope / max(mean_r, 1.0)

        # 6. Output Indices
        predictability_idx = clamp(100.0 - (cv * 100.0))
        trajectory_idx = clamp(50.0 + (norm_trend * 500.0))

        # 7. Verdict Determination
        if cv <= 0.3:
            verdict = "CONSISTENT_FLOWS"
        elif cv <= 0.6:
            verdict = "MODERATE_VOLATILITY"
        else:
            verdict = "HIGHLY_ERRATIC_FLOWS"

        report = (
            f"[SUBMODULE 4.7: CASH FLOW STABILITY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Revenue Predictability Index: {predictability_idx:.1f} / 100.0\n"
            f"- Revenue Trajectory Index: {trajectory_idx:.1f} / 100.0\n"
            f"SUMMARY: Mean monthly revenue: {mean_r:,.2f} MDL. "
            f"Coefficient of Variation: {cv:.2f}. "
            f"Revenue growth trajectory slope is {slope:.2f} per month."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
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


__all__ = [
    "CashflowStabilityEvaluator",
]
