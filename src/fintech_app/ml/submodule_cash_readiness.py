"""
Submodule 4.6: Immediate Cash Readiness Evaluator (ICR).
Evaluates total liquid cash against immediate 30-day operational obligations (payroll, taxes, due payables).
Calculates Cash Ratio (CR) and Days Cash on Hand (DCOH).
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class ImmediateCashReadinessEvaluator:
    """Evaluates short-term liquidity, cash ratio, and operational runway buffer."""

    def __init__(self) -> None:
        self.code = "ICR"
        self.impact_weight = 0.15

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        bank_accounts = getattr(snapshot, "bank_accounts", []) if snapshot else []
        transactions = getattr(snapshot, "transactions", []) if snapshot else []
        invoices = getattr(snapshot, "invoices", []) if snapshot else []

        if not bank_accounts:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Cash_Readiness_Index": None,
                    "Runway_Buffer_Index": None,
                },
                summary="No bank account records present.",
                diagnostic_report="[SUBMODULE 4.6: IMMEDIATE CASH READINESS]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        liquid_cash = sum(
            float(getattr(acc, "current_balance", 0.0)) + float(getattr(acc, "overdraft_limit", 0.0))
            for acc in bank_accounts
        )

        payroll_txs = [
            float(getattr(tx, "amount", 0.0)) for tx in transactions
            if str(getattr(tx, "direction", "")).upper() == "OUTFLOW"
            and str(getattr(tx, "category", "")).upper() == "PAYROLL"
        ]
        tax_txs = [
            float(getattr(tx, "amount", 0.0)) for tx in transactions
            if str(getattr(tx, "direction", "")).upper() == "OUTFLOW"
            and str(getattr(tx, "category", "")).upper() == "TAX"
        ]

        monthly_payroll = sum(payroll_txs) / 3.0 if payroll_txs else 0.0
        monthly_taxes = sum(tax_txs) / 3.0 if tax_txs else 0.0

        due_payables_30d = sum(
            float(getattr(inv, "gross_amount", 0.0)) for inv in invoices
            if str(getattr(inv, "invoice_type", "")).upper() == "PAYABLE"
            and str(getattr(inv, "status", "")).upper() in ("OUTSTANDING", "OVERDUE")
        )

        total_demand = monthly_payroll + monthly_taxes + due_payables_30d
        cash_ratio = liquid_cash / max(total_demand, 1.0)

        daily_burn = (monthly_payroll + monthly_taxes) / 30.0
        dcoh = liquid_cash / max(daily_burn, 1.0) if daily_burn > 0 else 999.0

        cash_readiness_idx = max(0.0, min(100.0, cash_ratio * 50.0))
        runway_buffer_idx = max(0.0, min(100.0, (dcoh / 60.0) * 100.0))

        if cash_ratio >= 1.5:
            verdict = "LIQUID_AND_SOLVENT"
        elif cash_ratio >= 1.0:
            verdict = "POTENTIAL_CASH_GAP"
        else:
            verdict = "SEVERE_ILLIQUIDITY"

        report = (
            f"[SUBMODULE 4.6: IMMEDIATE CASH READINESS]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Cash Readiness Index: {cash_readiness_idx:.1f} / 100.0\n"
            f"- Runway Buffer Index: {runway_buffer_idx:.1f} / 100.0\n"
            f"SUMMARY: Available liquidity: {liquid_cash:,.2f} MDL. Immediate 30-day obligations: "
            f"{total_demand:,.2f} MDL. Cash Ratio is {cash_ratio:.2f}. Company maintains {dcoh:.1f} days cash runway."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Cash_Readiness_Index": cash_readiness_idx,
                "Runway_Buffer_Index": runway_buffer_idx,
            },
            summary=f"Cash Ratio: {cash_ratio:.2f}, DCOH: {dcoh:.1f} days.",
            diagnostic_report=report,
        )

