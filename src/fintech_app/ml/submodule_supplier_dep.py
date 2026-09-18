"""
Submodule 4.5: Supplier Dependency Evaluator (SD).
Evaluates vendor spend concentration (HHI) and primary vendor dependency.
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class SupplierDependencyEvaluator:
    """Evaluates supplier concentration and supply chain robustness."""

    def __init__(self) -> None:
        self.code = "SD"
        self.impact_weight = 0.08

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        invoices = getattr(snapshot, "invoices", []) if snapshot else []
        payables = [
            inv for inv in invoices
            if str(getattr(inv, "invoice_type", "")).upper() == "PAYABLE"
            and str(getattr(inv, "status", "")).upper() == "PAID"
        ]

        if not payables:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Supplier_Diversification_Index": None,
                    "Supply_Chain_Robustness_Index": None,
                },
                summary="No payable invoice records present.",
                diagnostic_report="[SUBMODULE 4.5: SUPPLIER DEPENDENCY]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        vendor_spend: dict = {}
        for inv in payables:
            vid = str(getattr(inv, "counterparty_id", "unknown"))
            amt = float(getattr(inv, "gross_amount", 0.0))
            vendor_spend[vid] = vendor_spend.get(vid, 0.0) + amt

        total_spend = sum(vendor_spend.values())
        if total_spend <= 0:
            total_spend = 1.0

        shares = [(amt / total_spend) * 100.0 for amt in vendor_spend.values()]
        vendor_hhi = sum(s ** 2 for s in shares)
        primary_vendor_share = max(shares) if shares else 0.0

        diversification_idx = max(0.0, min(100.0, 100.0 - (vendor_hhi / 100.0)))
        robustness_idx = max(0.0, min(100.0, 100.0 - primary_vendor_share))

        verdict = "DIVERSIFIED_SUPPLY_CHAIN" if primary_vendor_share < 40.0 else "MONOPOLISTIC_SUPPLIER_RISK"

        report = (
            f"[SUBMODULE 4.5: SUPPLIER DEPENDENCY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Supplier Diversification Index: {diversification_idx:.1f} / 100.0\n"
            f"- Supply Chain Robustness Index: {robustness_idx:.1f} / 100.0\n"
            f"SUMMARY: Vendor HHI is {vendor_hhi:.1f}. Largest supplier consumes "
            f"{primary_vendor_share:.1f}% of total procurement expenditures across {len(vendor_spend)} active suppliers."
        )

        return SubmoduleResult(
            submodule_code=self.code,
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

