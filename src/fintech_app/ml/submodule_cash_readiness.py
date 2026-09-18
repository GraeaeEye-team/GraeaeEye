"""
Submodule 4.6: Immediate Cash Readiness Evaluator (ICR).
Evaluates total liquid cash against immediate 30-day operational obligations (payroll, taxes, due payables).
Calculates Cash Ratio (CR) and Days Cash on Hand (DCOH).
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


class ImmediateCashReadinessEvaluator(BaseSubmoduleEvaluator):
    """Evaluates short-term liquidity, cash ratio, and operational runway buffer."""

    submodule_code: str = "ICR"
    impact_weight: float = 0.15

    def __init__(self) -> None:
        super().__init__(submodule_code="ICR", impact_weight=0.15)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        bank_accounts = getattr(snapshot, "bank_accounts", []) if snapshot else []
        transactions = getattr(snapshot, "transactions", []) if snapshot else []
        invoices = getattr(snapshot, "invoices", []) if snapshot else []

        if not bank_accounts:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Cash_Readiness_Index": None,
                    "Runway_Buffer_Index": None,
                },
                summary="No bank account records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.6: IMMEDIATE CASH READINESS]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        # 1. Available Liquidity (MDL accounts)
        mdl_accounts = [
            acc for acc in bank_accounts
            if str(getattr(acc, "currency", "MDL")).upper() == "MDL"
        ]
        # Fallback to all bank accounts if none explicitly marked MDL
        active_accounts = mdl_accounts if mdl_accounts else bank_accounts

        liquid_cash = sum(
            float(getattr(acc, "current_balance", 0.0)) + float(getattr(acc, "overdraft_limit", 0.0))
            for acc in active_accounts
        )

        # Determine evaluation date
        raw_as_of = getattr(snapshot, "as_of_date", None)
        if raw_as_of is None:
            as_of_date = date.today()
        elif isinstance(raw_as_of, datetime):
            as_of_date = raw_as_of.date()
        else:
            as_of_date = raw_as_of

        # 2. Monthly Payroll and Taxes: Average monthly outflow over trailing 3 months (90 days)
        three_months_ago = as_of_date - timedelta(days=90)

        payroll_amounts = []
        tax_amounts = []
        for tx in transactions:
            direction = str(getattr(tx, "direction", "")).upper()
            category = str(getattr(tx, "category", "")).upper()
            if direction == "OUTFLOW":
                tx_date = getattr(tx, "timestamp", None) or getattr(tx, "transaction_date", None)
                if isinstance(tx_date, datetime):
                    tx_date = tx_date.date()
                if tx_date is not None and (tx_date < three_months_ago or tx_date > as_of_date):
                    continue

                amt = float(getattr(tx, "amount", 0.0))
                if category == "PAYROLL":
                    payroll_amounts.append(amt)
                elif category == "TAX":
                    tax_amounts.append(amt)

        monthly_payroll = sum(payroll_amounts) / 3.0 if payroll_amounts else 0.0
        monthly_taxes = sum(tax_amounts) / 3.0 if tax_amounts else 0.0

        # 3. Due Payables 30D: PAYABLE invoices with status OUTSTANDING (or OVERDUE) and due_date <= as_of_date + 30 days
        due_payables_30d = 0.0
        max_due_date = as_of_date + timedelta(days=30)
        for inv in invoices:
            inv_type = str(getattr(inv, "invoice_type", "")).upper()
            status = str(getattr(inv, "status", "")).upper()
            if inv_type == "PAYABLE" and status in ("OUTSTANDING", "OVERDUE"):
                due_date = getattr(inv, "due_date", None)
                if isinstance(due_date, datetime):
                    due_date = due_date.date()
                if due_date is not None and due_date > max_due_date:
                    continue
                due_payables_30d += float(getattr(inv, "gross_amount", 0.0))

        # 4. Total Immediate Demand & Liquidity Ratios
        total_demand = monthly_payroll + monthly_taxes + due_payables_30d
        cash_ratio = liquid_cash / max(total_demand, 1.0)

        daily_burn = (monthly_payroll + monthly_taxes) / 30.0
        dcoh = liquid_cash / max(daily_burn, 1.0)

        # 5. Output Indices
        cash_readiness_idx = clamp(cash_ratio * 50.0)  # CR >= 2.0 -> 100.0
        runway_buffer_idx = clamp((dcoh / 60.0) * 100.0)  # 60+ days -> 100.0

        # 6. Verdict Determination
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
            submodule_code=self.submodule_code,
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


__all__ = [
    "ImmediateCashReadinessEvaluator",
]
