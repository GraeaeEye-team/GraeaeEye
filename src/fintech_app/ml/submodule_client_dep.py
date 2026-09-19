"""
Submodule 4.4: Client Dependency Evaluator (CD).
Calculates customer concentration (Customer_HHI) and top buyer exposure ratios (CR1, CR3)
over the trailing 12-month period from the evaluation snapshot.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

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


class ClientDependencyEvaluator(BaseSubmoduleEvaluator):
    """
    Evaluates customer concentration, buyer dependency,
    and revenue single-point-of-failure risk.
    """

    submodule_code: str = "CD"
    impact_weight: float = 0.10

    def __init__(self) -> None:
        super().__init__(submodule_code="CD", impact_weight=0.10)

    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        invoices = getattr(snapshot, "invoices", []) if snapshot else []
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

        # Filter closed receivable invoices within the trailing 12-month window
        receivables = []
        for inv in invoices:
            inv_type = str(getattr(inv, "invoice_type", "")).upper()
            status = str(getattr(inv, "status", "")).upper()
            if inv_type == "RECEIVABLE" and status in ("SETTLED", "PAID"):
                # Check period if date attribute exists
                doc_date = (
                    getattr(inv, "actual_payment_date", None)
                    or getattr(inv, "issue_date", None)
                )
                if isinstance(doc_date, datetime):
                    doc_date = doc_date.date()
                if doc_date is not None and (doc_date < start_date or doc_date > as_of_date):
                    continue
                receivables.append(inv)

        if not receivables:
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Client_Diversification_Index": None,
                    "Top_Client_Exposure_Index": None,
                },
                summary="No receivable invoice records present.",
                diagnostic_report=(
                    "[SUBMODULE 4.4: CLIENT DEPENDENCY]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        # 1. Aggregate Revenue per Client in Decimal
        client_revenue: dict[str, Decimal] = {}
        for inv in receivables:
            cid = str(getattr(inv, "counterparty_id", "unknown"))
            raw_amt = getattr(inv, "gross_amount", Decimal("0.00"))
            amt = raw_amt if isinstance(raw_amt, Decimal) else Decimal(str(raw_amt))
            client_revenue[cid] = client_revenue.get(cid, Decimal("0.00")) + amt

        total_rev_dec = sum(client_revenue.values(), Decimal("0.00"))
        if total_rev_dec <= Decimal("0.00"):
            return SubmoduleResult(
                submodule_code=self.submodule_code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={
                    "Client_Diversification_Index": None,
                    "Top_Client_Exposure_Index": None,
                },
                summary="Total commercial revenue is zero.",
                diagnostic_report=(
                    "[SUBMODULE 4.4: CLIENT DEPENDENCY]\n"
                    "STATUS: DATA_ABSENT\n"
                    "VERDICT: DATA_ABSENT"
                ),
            )

        # 2. Final stage computation: convert to float for indices and ratios
        total_rev = float(total_rev_dec)
        sorted_clients = sorted(client_revenue.items(), key=lambda item: item[1], reverse=True)
        shares = [(float(amt) / total_rev) * 100.0 for _, amt in sorted_clients]

        # 3. Customer Herfindahl-Hirschman Index (Customer_HHI)
        customer_hhi = sum(s ** 2 for s in shares)

        # 4. Top-1 (CR1) and Top-3 (CR3) Concentration Ratios
        cr1 = shares[0] if shares else 0.0
        cr3 = sum(shares[:3]) if len(shares) >= 3 else sum(shares)

        # 5. Output Indices
        diversification_idx = clamp(100.0 - (customer_hhi / 100.0))
        top_exposure_idx = clamp(100.0 - cr1)

        # 6. Verdict Determination
        if cr1 < 30.0:
            verdict = "BROAD_CLIENT_BASE"
        elif cr1 < 50.0:
            verdict = "MODERATE_CONCENTRATION"
        else:
            verdict = "SEVERE_CLIENT_DEPENDENCY"

        # Build counterparty names lookup for informative reporting
        cp_names = {
            str(getattr(cp, "counterparty_id", "")): getattr(
                cp, "legal_name", str(getattr(cp, "counterparty_id", ""))
            )
            for cp in counterparties
        }
        top_client_id = sorted_clients[0][0] if sorted_clients else "N/A"
        top_client_label = cp_names.get(top_client_id, top_client_id)
        client_label_info = f" ({top_client_label})" if top_client_label != top_client_id else ""

        report = (
            f"[SUBMODULE 4.4: CLIENT DEPENDENCY]\n"
            f"VERDICT: {verdict}\n"
            f"IMPACT WEIGHT: {self.impact_weight}\n"
            f"NUMERICAL INDICES:\n"
            f"- Client Diversification Index: {diversification_idx:.1f} / 100.0\n"
            f"- Top Client Exposure Index: {top_exposure_idx:.1f} / 100.0\n"
            f"SUMMARY: Customer HHI is {customer_hhi:.1f}. "
            f"Primary client{client_label_info} accounts for {cr1:.1f}%, "
            f"and top 3 clients represent {cr3:.1f}% of total trailing 12-month revenue."
        )

        return SubmoduleResult(
            submodule_code=self.submodule_code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict=verdict,
            indices={
                "Client_Diversification_Index": diversification_idx,
                "Top_Client_Exposure_Index": top_exposure_idx,
            },
            summary=f"Customer HHI: {customer_hhi:.1f}, CR1: {cr1:.1f}%, CR3: {cr3:.1f}%.",
            diagnostic_report=report,
        )


__all__ = [
    "ClientDependencyEvaluator",
]
