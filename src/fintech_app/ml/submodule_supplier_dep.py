"""
Submodule 4.5: Supplier Dependency Evaluator (SD).
Evaluates vendor spend concentration (Vendor_HHI) and primary vendor exposure
across paid payable invoices and operating expenditure transactions over the trailing 12 months.
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


class SupplierDependencyEvaluator(BaseSubmoduleEvaluator):
    """Evaluates supplier concentration, procurement single-source vulnerability, and supply chain robustness."""

    submodule_code: str = "SD"
    impact_weight: float = 0.08

    def __init__(self) -> None:
        super().__init__(submodule_code="SD", impact_weight=0.08)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        invoices = getattr(snapshot, "invoices", []) if snapshot else []
        transactions = getattr(snapshot, "transactions", []) if snapshot else []
        counterparties = getattr(snapshot, "counterparties", []) if snapshot else []

        # Determine cutoff window: trailing 12 months (365 days) from snapshot.as_of_date
        raw_as_of = getattr(snapshot, "as_of_date", None)
        if raw_as_of is None:
            as_of_date = date.today()
        elif isinstance(raw_as_of, datetime):
            as_of_date = raw_as_of.date()
        else:
            as_of_date = raw_as_of

        start_date = as_of_date - timedelta(days=365)

        # 1. Filter closed payable invoices within the trailing 12-month window
        payables = []
        counted_invoice_ids = set()
        for inv in invoices:
            inv_type = str(getattr(inv, "invoice_type", "")).upper()
            status = str(getattr(inv, "status", "")).upper()
            if inv_type == "PAYABLE" and status == "PAID":
                doc_date = getattr(inv, "actual_payment_date", None) or getattr(inv, "issue_date", None)
                if isinstance(doc_date, datetime):
                    doc_date = doc_date.date()
                if doc_date is not None and (doc_date < start_date or doc_date > as_of_date):
                    continue
                payables.append(inv)
                inv_id = getattr(inv, "invoice_id", None)
                if inv_id is not None:
                    counted_invoice_ids.add(str(inv_id))

        # 2. Filter operating expense outflow transactions within the window
        opex_transactions = []
        for tx in transactions:
            direction = str(getattr(tx, "direction", "")).upper()
            category = str(getattr(tx, "category", "")).upper()
            if direction == "OUTFLOW" and category == "OPERATING_EXPENSE":
                tx_date = getattr(tx, "timestamp", None) or getattr(tx, "transaction_date", None)
                if isinstance(tx_date, datetime):
                    tx_date = tx_date.date()
                if tx_date is not None and (tx_date < start_date or tx_date > as_of_date):
                    continue
                # Skip transactions already accounted for by a processed invoice
                tx_inv_id = getattr(tx, "invoice_id", None)
                if tx_inv_id is not None and str(tx_inv_id) in counted_invoice_ids:
                    continue
                opex_transactions.append(tx)

        # 3. Accumulate spend per vendor in Decimal
        vendor_spend: dict[str, Decimal] = {}

        for inv in payables:
            vid = str(getattr(inv, "counterparty_id", "unknown"))
            raw_amt = getattr(inv, "gross_amount", Decimal("0.00"))
            amt = raw_amt if isinstance(raw_amt, Decimal) else Decimal(str(raw_amt))
            vendor_spend[vid] = vendor_spend.get(vid, Decimal("0.00")) + amt

        for tx in opex_transactions:
            raw_cid = getattr(tx, "counterparty_id", None)
            if raw_cid is None:
                continue
            vid = str(raw_cid)
            raw_amt = getattr(tx, "amount", Decimal("0.00"))
            amt = raw_amt if isinstance(raw_amt, Decimal) else Decimal(str(raw_amt))
            vendor_spend[vid] = vendor_spend.get(vid, Decimal("0.00")) + amt

        total_spend_dec = sum(vendor_spend.values(), Decimal("0.00"))

        if not vendor_spend or total_spend_dec <= Decimal("0.00"):
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Supplier_Diversification_Index": None,
                    "Supply_Chain_Robustness_Index": None,
                },
                summary="No payable invoice or vendor expenditure records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.5: SUPPLIER DEPENDENCY]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        # 4. Final stage computation: convert to float for indices and ratios
        total_spend = float(total_spend_dec)
        sorted_vendors = sorted(vendor_spend.items(), key=lambda item: item[1], reverse=True)
        shares = [(float(amt) / total_spend) * 100.0 for _, amt in sorted_vendors]

        # 5. Vendor Herfindahl-Hirschman Index (Vendor_HHI)
        vendor_hhi = sum(s ** 2 for s in shares)

        # 6. Primary Vendor Dependency Ratio
        primary_vendor_share = shares[0] if shares else 0.0

        # 7. Output Indices
        diversification_idx = clamp(100.0 - (vendor_hhi / 100.0))
        robustness_idx = clamp(100.0 - primary_vendor_share)

        # 8. Verdict Determination
        verdict = (
            "DIVERSIFIED_SUPPLY_CHAIN"
            if primary_vendor_share < 40.0
            else "MONOPOLISTIC_SUPPLIER_RISK"
        )

        # Build counterparty names lookup for diagnostic report
        cp_names = {
            str(getattr(cp, "counterparty_id", "")): getattr(cp, "legal_name", str(getattr(cp, "counterparty_id", "")))
            for cp in counterparties
        }
        top_vendor_id = sorted_vendors[0][0] if sorted_vendors else "N/A"
        top_vendor_label = cp_names.get(top_vendor_id, top_vendor_id)
        vendor_label_info = f" ({top_vendor_label})" if top_vendor_label != top_vendor_id else ""

        report = (
            f"[SUBMODULE 4.5: SUPPLIER DEPENDENCY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Supplier Diversification Index: {diversification_idx:.1f} / 100.0\n"
            f"- Supply Chain Robustness Index: {robustness_idx:.1f} / 100.0\n"
            f"SUMMARY: Vendor HHI is {vendor_hhi:.1f}. Largest supplier{vendor_label_info} consumes "
            f"{primary_vendor_share:.1f}% of total procurement expenditures across {len(vendor_spend)} active operational suppliers."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Supplier_Diversification_Index": diversification_idx,
                "Supply_Chain_Robustness_Index": robustness_idx,
            },
            summary=f"Vendor HHI: {vendor_hhi:.1f}, Top Supplier Share: {primary_vendor_share:.1f}%.",
            diagnostic_report=report,
        )


__all__ = [
    "SupplierDependencyEvaluator",
]
