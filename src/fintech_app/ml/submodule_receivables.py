"""
Submodule 4.8: Receivables Quality Evaluator (RQ).
Evaluates trapped working capital, delinquent receivables exposure (CER), customer payment slippage, and DSO.
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class ReceivablesQualityEvaluator:
    """Evaluates receivables aging, payment delay slippage, and Days Sales Outstanding (DSO)."""

    def __init__(self) -> None:
        self.code = "RQ"
        self.impact_weight = 0.14

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        invoices = getattr(snapshot, "invoices", []) if snapshot else []
        receivables = [
            inv for inv in invoices
            if str(getattr(inv, "invoice_type", "")).upper() == "RECEIVABLE"
        ]

        if not receivables:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Receivables_Safety_Index": None,
                    "Client_Payment_Discipline_Index": None,
                },
                summary="No receivable invoice records present.",
                diagnostic_report="[SUBMODULE 4.8: RECEIVABLES QUALITY]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        total_rec = sum(
            float(getattr(inv, "gross_amount", 0.0)) for inv in receivables
            if str(getattr(inv, "status", "")).upper() != "PAID"
        )
        delinquent_rec = sum(
            float(getattr(inv, "gross_amount", 0.0)) for inv in receivables
            if str(getattr(inv, "status", "")).upper() in ("OVERDUE", "DEFAULTED")
        )

        cer = delinquent_rec / max(total_rec, 1.0)

        delays = []
        for inv in receivables:
            status = str(getattr(inv, "status", "")).upper()
            if status == "PAID":
                actual_date = getattr(inv, "actual_payment_date", None)
                due_date = getattr(inv, "due_date", None)
                if actual_date and due_date:
                    try:
                        delay = (actual_date - due_date).days
                        delays.append(max(0, delay))
                    except Exception:
                        pass

        mean_delay = sum(delays) / len(delays) if delays else 0.0
        annual_credit_sales = sum(float(getattr(inv, "gross_amount", 0.0)) for inv in receivables)
        dso = (total_rec / max(annual_credit_sales, 1.0)) * 365.0

        receivables_safety_idx = max(0.0, min(100.0, 100.0 - (cer * 100.0)))
        discipline_idx = max(0.0, min(100.0, 100.0 - (mean_delay * 2.0)))

        verdict = "PROMPT_COLLECTIONS" if cer <= 0.1 and mean_delay <= 10 else ("MODERATE_SLIPPAGE" if cer <= 0.3 else "FROZEN_DEBT_RISK")

        report = (
            f"[SUBMODULE 4.8: RECEIVABLES QUALITY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Receivables Safety Index: {receivables_safety_idx:.1f} / 100.0\n"
            f"- Client Payment Discipline Index: {discipline_idx:.1f} / 100.0\n"
            f"SUMMARY: Delinquent receivables represent {cer * 100:.1f}% of total book receivables. "
            f"Average payment delay past contractual due date is {mean_delay:.1f} days. DSO stands at {dso:.1f} days."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Receivables_Safety_Index": receivables_safety_idx,
                "Client_Payment_Discipline_Index": discipline_idx,
            },
            summary=f"Delinquency Exposure (CER): {cer * 100:.1f}%, Mean Delay: {mean_delay:.1f} days.",
            diagnostic_report=report,
        )

