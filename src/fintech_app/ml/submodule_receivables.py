"""
Submodule 4.8: Receivables Quality Evaluator (RQ).
Evaluates trapped working capital, delinquent receivables exposure (CER),
customer payment slippage (Mean_Delay_Days), and Days Sales Outstanding (DSO).
"""

from datetime import date, datetime, timedelta
from typing import Any, Optional

try:
    from src.fintech_app.ml.base import (
        BaseSubmoduleEvaluator,
        SubmoduleResult,
        clamp,
    )
    from src.fintech_app.shared.schemas.user_types import EvaluationStatus
except ModuleNotFoundError:
    from fintech_app.ml.base import (
        BaseSubmoduleEvaluator,
        SubmoduleResult,
        clamp,
    )
    from fintech_app.shared.schemas.user_types import EvaluationStatus


class ReceivablesQualityEvaluator(BaseSubmoduleEvaluator):
    """Evaluates receivables aging, payment delay slippage, and Days Sales Outstanding (DSO)."""

    submodule_code: str = "RQ"
    impact_weight: float = 0.14

    def __init__(self) -> None:
        super().__init__(submodule_code="RQ", impact_weight=0.14)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        invoices = getattr(snapshot, "invoices", []) if snapshot else []
        receivables = [inv for inv in invoices if str(getattr(inv, "invoice_type", "")).upper() == "RECEIVABLE"]

        if not receivables:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Receivables_Safety_Index": None,
                    "Client_Payment_Discipline_Index": None,
                },
                summary="No receivable invoice records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.8: RECEIVABLES QUALITY]\n" "STATUS: DATA_ABSENT\n" "VERDICT: DATA_ABSENT"
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

        # 1. Total Receivables and Delinquent Receivables
        total_rec = sum(
            float(getattr(inv, "gross_amount", 0.0))
            for inv in receivables
            if str(getattr(inv, "status", "")).upper() not in ("SETTLED", "PAID")
        )
        delinquent_rec = sum(
            float(getattr(inv, "gross_amount", 0.0))
            for inv in receivables
            if str(getattr(inv, "status", "")).upper() in ("OVERDUE", "DEFAULTED", "DISPUTED")
        )

        # Counterparty Exposure Ratio (CER)
        cer = delinquent_rec / max(total_rec, 1.0)

        # 2. Behavioral Payment Delay (Slippage) across settled invoices in trailing 12 months
        delays = []
        for inv in receivables:
            status = str(getattr(inv, "status", "")).upper()
            if status in ("SETTLED", "PAID"):
                actual_date = getattr(inv, "actual_payment_date", None)
                due_date = getattr(inv, "due_date", None)
                if isinstance(actual_date, datetime):
                    actual_date = actual_date.date()
                if isinstance(due_date, datetime):
                    due_date = due_date.date()

                # Filter settled invoices within trailing 12 months if date present
                if actual_date is not None and (actual_date < one_year_ago or actual_date > as_of_date):
                    continue

                if actual_date and due_date:
                    delay_days = (actual_date - due_date).days
                    delays.append(max(0, delay_days))

        mean_delay = sum(delays) / len(delays) if delays else 0.0

        # 3. Days Sales Outstanding (DSO)
        def _get_issue_dt(inv: Any) -> Optional[date]:
            dt = getattr(inv, "issue_date", None)
            if isinstance(dt, datetime):
                return dt.date()
            return dt

        credit_sales_invoices = [
            inv for inv in receivables if _get_issue_dt(inv) is None or _get_issue_dt(inv) >= one_year_ago
        ]
        annual_credit_sales = sum(float(getattr(inv, "gross_amount", 0.0)) for inv in credit_sales_invoices)
        if annual_credit_sales <= 0.0:
            annual_credit_sales = sum(float(getattr(inv, "gross_amount", 0.0)) for inv in receivables)

        dso = (total_rec / max(annual_credit_sales, 1.0)) * 365.0

        # 4. Output Indices
        receivables_safety_idx = clamp(100.0 - (cer * 100.0))
        discipline_idx = clamp(100.0 - (mean_delay * 2.0))

        # 5. Verdict Determination
        if cer <= 0.1 and mean_delay <= 10.0:
            verdict = "PROMPT_COLLECTIONS"
        elif cer <= 0.3:
            verdict = "MODERATE_SLIPPAGE"
        else:
            verdict = "FROZEN_DEBT_RISK"

        report = (
            f"[SUBMODULE 4.8: RECEIVABLES QUALITY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Receivables Safety Index: {receivables_safety_idx:.1f} / 100.0\n"
            f"- Client Payment Discipline Index: {discipline_idx:.1f} / 100.0\n"
            f"SUMMARY: Delinquent receivables represent {cer * 100.0:.1f}% "
            f"of total book receivables. Average payment delay past contractual "
            f"due date is {mean_delay:.1f} days. DSO stands at {dso:.1f} days."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Receivables_Safety_Index": receivables_safety_idx,
                "Client_Payment_Discipline_Index": discipline_idx,
            },
            summary=(f"Delinquency Exposure (CER): {cer * 100.0:.1f}%, " f"Mean Delay: {mean_delay:.1f} days."),
            diagnostic_report=report,
        )


__all__ = [
    "ReceivablesQualityEvaluator",
]
