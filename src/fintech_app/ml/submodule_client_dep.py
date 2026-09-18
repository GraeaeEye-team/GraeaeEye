"""
Submodule 4.4: Client Dependency Evaluator (CD).
Calculates customer concentration (HHI) and top customer exposure (CR1 / CR3).
"""
from typing import Any
from fintech_app.ml.submodule_ownership import SubmoduleResult
from fintech_app.shared.schemas.user_types import EvaluationStatus


class ClientDependencyEvaluator:
    """Evaluates customer concentration and top buyer exposure ratios."""

    def __init__(self) -> None:
        self.code = "CD"
        self.impact_weight = 0.10

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        invoices = getattr(snapshot, "invoices", []) if snapshot else []
        receivables = [
            inv for inv in invoices
            if str(getattr(inv, "invoice_type", "")).upper() == "RECEIVABLE"
            and str(getattr(inv, "status", "")).upper() == "PAID"
        ]

        if not receivables:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Client_Diversification_Index": None,
                    "Top_Client_Exposure_Index": None,
                },
                summary="No receivable invoice records present.",
                diagnostic_report="[SUBMODULE 4.4: CLIENT DEPENDENCY]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED",
            )

        client_revenue: dict = {}
        for inv in receivables:
            cid = str(getattr(inv, "counterparty_id", "unknown"))
            amt = float(getattr(inv, "gross_amount", 0.0))
            client_revenue[cid] = client_revenue.get(cid, 0.0) + amt

        total_rev = sum(client_revenue.values())
        if total_rev <= 0:
            total_rev = 1.0

        shares = [(amt / total_rev) * 100.0 for amt in client_revenue.values()]
        customer_hhi = sum(s ** 2 for s in shares)

        sorted_shares = sorted(shares, reverse=True)
        cr1 = sorted_shares[0] if sorted_shares else 0.0
        cr3 = sum(sorted_shares[:3]) if len(sorted_shares) >= 3 else sum(sorted_shares)

        diversification_idx = max(0.0, min(100.0, 100.0 - (customer_hhi / 100.0)))
        top_exposure_idx = max(0.0, min(100.0, 100.0 - cr1))

        verdict = "BROAD_CLIENT_BASE" if cr1 < 30.0 else ("MODERATE_CONCENTRATION" if cr1 < 50.0 else "SEVERE_CLIENT_DEPENDENCY")

        report = (
            f"[SUBMODULE 4.4: CLIENT DEPENDENCY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Client Diversification Index: {diversification_idx:.1f} / 100.0\n"
            f"- Top Client Exposure Index: {top_exposure_idx:.1f} / 100.0\n"
            f"SUMMARY: Customer HHI is {customer_hhi:.1f}. Primary client accounts for {cr1:.1f}%, "
            f"and top 3 clients represent {cr3:.1f}% of total commercial revenue."
        )

        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Client_Diversification_Index": diversification_idx,
                "Top_Client_Exposure_Index": top_exposure_idx,
            },
            summary=f"Customer HHI: {customer_hhi:.1f}, CR1: {cr1:.1f}%.",
            diagnostic_report=report,
        )

