"""
Submodule 4.9: Credit Discipline & Leverage Evaluator (ICDL).
Evaluates past delinquencies penalties (30d/90d DPD, defaults), Debt Service Coverage Ratio (DSCR),
and Debt-to-Cash Flow Leverage (DCFL).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

try:
    from src.fintech_app.ml.base import (
        BaseSubmoduleEvaluator,
        SubmoduleResult,
        clamp,
        safe_div,
    )
    from src.fintech_app.shared.schemas.user_types import EvaluationStatus
except ModuleNotFoundError:
    from fintech_app.ml.base import (
        BaseSubmoduleEvaluator,
        SubmoduleResult,
        clamp,
        safe_div,
    )
    from fintech_app.shared.schemas.user_types import EvaluationStatus


class CreditDisciplineLeverageEvaluator(BaseSubmoduleEvaluator):
    """Evaluates historical repayment discipline, DSCR coverage, and debt leverage."""

    submodule_code: str = "ICDL"
    impact_weight: float = 0.16

    def __init__(self) -> None:
        super().__init__(submodule_code="ICDL", impact_weight=0.16)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        obligations = getattr(snapshot, "credit_obligations", []) if snapshot else []
        transactions = getattr(snapshot, "transactions", []) if snapshot else []

        # Graceful degradation if no credit obligations exist
        if not obligations:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Debt_Repayment_Discipline_Index": None,
                    "Debt_Service_Coverage_Index": None,
                    "Solvency_Leverage_Index": None,
                },
                summary="No credit obligation records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.9: INTERNAL CREDIT DISCIPLINE & LEVERAGE]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        raw_as_of = getattr(snapshot, "as_of_date", None)
        if raw_as_of is None:
            as_of_date = date.today()
        elif isinstance(raw_as_of, datetime):
            as_of_date = raw_as_of.date()
        else:
            as_of_date = raw_as_of

        one_year_ago = as_of_date - timedelta(days=365)

        # 1. Historical Delinquencies & Penalty
        past_due_30d = sum(int(getattr(ob, "past_due_30d_count", 0)) for ob in obligations)
        past_due_90d = sum(int(getattr(ob, "past_due_90d_count", 0)) for ob in obligations)
        defaults_count = sum(int(getattr(ob, "historical_defaults_count", 0)) for ob in obligations)

        dpd_penalty = (past_due_30d * 10.0) + (past_due_90d * 25.0) + (defaults_count * 50.0)
        repayment_discipline_idx = clamp(100.0 - dpd_penalty)

        # 2. Annual Operating Cash Flow (trailing 12 months)
        annual_inflows = 0.0
        annual_opex = 0.0
        for tx in transactions:
            tx_date = getattr(tx, "timestamp", None) or getattr(tx, "transaction_date", None)
            if isinstance(tx_date, datetime):
                tx_date = tx_date.date()
            if tx_date is not None and (tx_date < one_year_ago or tx_date > as_of_date):
                continue

            direction = str(getattr(tx, "direction", "")).upper()
            category = str(getattr(tx, "category", "")).upper()
            amt = float(getattr(tx, "amount", 0.0))

            if direction == "INFLOW":
                annual_inflows += amt
            elif direction == "OUTFLOW" and category != "DEBT_SERVICE":
                annual_opex += amt

        operating_cash_flow = max(0.0, annual_inflows - annual_opex)

        # 3. Debt Service Coverage Ratio (DSCR)
        annual_debt_service = sum(float(getattr(ob, "monthly_payment", 0.0)) * 12.0 for ob in obligations)
        dscr = operating_cash_flow / max(annual_debt_service, 1.0)
        dscr_idx = clamp((dscr / 2.0) * 100.0)  # DSCR >= 2.0 gives 100.0

        # 4. Debt-to-Cash Flow Leverage (DCFL)
        total_debt = sum(float(getattr(ob, "outstanding_balance", 0.0)) for ob in obligations)
        dcfl = total_debt / max(operating_cash_flow, 1.0)
        solvency_leverage_idx = clamp(100.0 - (dcfl * 20.0))

        # 5. Verdict Determination
        if repayment_discipline_idx >= 80.0 and dscr >= 1.5:
            verdict = "PRISTINE_CREDIT"
        elif repayment_discipline_idx >= 50.0:
            verdict = "MODERATE_LEVERAGE"
        else:
            verdict = "OVERINDEBTED_DELINQUENT"

        report = (
            f"[SUBMODULE 4.9: INTERNAL CREDIT DISCIPLINE & LEVERAGE]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Debt Repayment Discipline Index: {repayment_discipline_idx:.1f} / 100.0\n"
            f"- Debt Service Coverage Index: {dscr_idx:.1f} / 100.0\n"
            f"- Solvency Leverage Index: {solvency_leverage_idx:.1f} / 100.0\n"
            f"SUMMARY: Historical defaults: {defaults_count}, 90-day DPD: {past_due_90d}, "
            f"30-day DPD: {past_due_30d}. Calculated DSCR is {dscr:.2f}, with Total Debt / OCF at {dcfl:.1f}x."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Debt_Repayment_Discipline_Index": repayment_discipline_idx,
                "Debt_Service_Coverage_Index": dscr_idx,
                "Solvency_Leverage_Index": solvency_leverage_idx,
            },
            summary=f"Repayment Discipline: {repayment_discipline_idx:.1f}, DSCR: {dscr:.2f}, DCFL: {dcfl:.1f}x.",
            diagnostic_report=report,
        )


__all__ = [
    "CreditDisciplineLeverageEvaluator",
]
