"""
Submodule 4.9: Credit Discipline & Leverage Evaluator (ICDL).
Evaluates past delinquencies penalties (30d/90d DPD, defaults), Debt Service Coverage Ratio (DSCR), and Debt-to-Cash Flow Leverage (DCFL).
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class CreditDisciplineLeverageEvaluator:
    """Evaluates historical repayment discipline, DSCR coverage, and debt leverage."""

    def __init__(self) -> None:
        self.code = "ICDL"
        self.impact_weight = 0.16

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        obligations = getattr(snapshot, "credit_obligations", []) if snapshot else []
        transactions = getattr(snapshot, "transactions", []) if snapshot else []

        if not obligations:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Debt_Repayment_Discipline_Index": None,
                    "Debt_Service_Coverage_Index": None,
                    "Solvency_Leverage_Index": None,
                },
                summary="No credit obligation records present.",
                diagnostic_report="[SUBMODULE 4.9: INTERNAL CREDIT DISCIPLINE & LEVERAGE]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        past_due_30d = sum(getattr(ob, "past_due_30d_count", 0) for ob in obligations)
        past_due_90d = sum(getattr(ob, "past_due_90d_count", 0) for ob in obligations)
        defaults_count = sum(getattr(ob, "historical_defaults_count", 0) for ob in obligations)

        dpd_penalty = (past_due_30d * 10.0) + (past_due_90d * 25.0) + (defaults_count * 50.0)
        repayment_discipline_idx = max(0.0, min(100.0, 100.0 - dpd_penalty))

        annual_inflows = sum(
            float(getattr(tx, "amount", 0.0)) for tx in transactions
            if str(getattr(tx, "direction", "")).upper() == "INFLOW"
        )
        annual_opex = sum(
            float(getattr(tx, "amount", 0.0)) for tx in transactions
            if str(getattr(tx, "direction", "")).upper() == "OUTFLOW"
            and str(getattr(tx, "category", "")).upper() != "DEBT_SERVICE"
        )

        ocf = max(0.0, annual_inflows - annual_opex)
        annual_debt_service = sum(float(getattr(ob, "monthly_payment", 0.0)) * 12.0 for ob in obligations)

        dscr = ocf / max(annual_debt_service, 1.0)
        total_debt = sum(float(getattr(ob, "outstanding_balance", 0.0)) for ob in obligations)
        dcfl = total_debt / max(ocf, 1.0)

        dscr_idx = max(0.0, min(100.0, (dscr / 2.0) * 100.0))
        solvency_leverage_idx = max(0.0, min(100.0, 100.0 - (dcfl * 20.0)))

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
            submodule_code=self.code,
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
