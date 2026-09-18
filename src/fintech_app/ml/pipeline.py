"""
Master Pipeline Orchestrator for the Underwriting Analytical Core.
Runs all 9 autonomous submodules concurrently against CompanyDataSnapshot,
builds the standardized 18-element feature vector, and compiles the diagnostic report dossier.
"""
from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Any
from uuid import UUID

try:
    from src.fintech_app.ml.base import EvaluationStatus, SubmoduleResult
    from src.fintech_app.ml.submodule_ownership import OwnershipStructureEvaluator
    from src.fintech_app.ml.submodule_reputation import WebReputationEvaluator
    from src.fintech_app.ml.submodule_macro import MacroSectorRiskEvaluator
    from src.fintech_app.ml.submodule_client_dep import ClientDependencyEvaluator
    from src.fintech_app.ml.submodule_supplier_dep import SupplierDependencyEvaluator
    from src.fintech_app.ml.submodule_cash_readiness import ImmediateCashReadinessEvaluator
    from src.fintech_app.ml.submodule_cash_stability import CashflowStabilityEvaluator
    from src.fintech_app.ml.submodule_receivables import ReceivablesQualityEvaluator
    from src.fintech_app.ml.submodule_credit_discipline import CreditDisciplineLeverageEvaluator
except ModuleNotFoundError:
    from fintech_app.ml.base import EvaluationStatus, SubmoduleResult
    from fintech_app.ml.submodule_ownership import OwnershipStructureEvaluator
    from fintech_app.ml.submodule_reputation import WebReputationEvaluator
    from fintech_app.ml.submodule_macro import MacroSectorRiskEvaluator
    from fintech_app.ml.submodule_client_dep import ClientDependencyEvaluator
    from fintech_app.ml.submodule_supplier_dep import SupplierDependencyEvaluator
    from fintech_app.ml.submodule_cash_readiness import ImmediateCashReadinessEvaluator
    from fintech_app.ml.submodule_cash_stability import CashflowStabilityEvaluator
    from fintech_app.ml.submodule_receivables import ReceivablesQualityEvaluator
    from fintech_app.ml.submodule_credit_discipline import CreditDisciplineLeverageEvaluator

logger: logging.Logger = logging.getLogger("smart_credit.ml")


@dataclass
class UnderwritingPipelineResult:
    """Result of the complete 9-submodule analytical pipeline run."""

    business_id: UUID
    as_of_date: date
    feature_vector: list[float | None]  # Exactly 18 numerical indices in canonical order
    submodule_results: dict[str, SubmoduleResult]
    compiled_dossier_text: str


class UnderwritingAnalyticalPipeline:
    """Orchestrates sequential execution of all 9 analytical submodules with exception isolation."""

    SUBMODULE_EMPTY_INDICES: dict[str, dict[str, float | None]] = {
        "OS": {
            "Ownership_Dispersion_Index": None,
            "Governance_Independence_Index": None,
        },
        "WPR": {
            "Legal_Cleanliness_Index": None,
            "Public_Reputation_Index": None,
        },
        "MSR": {
            "Sector_Vitality_Index": None,
        },
        "CD": {
            "Client_Diversification_Index": None,
            "Top_Client_Exposure_Index": None,
        },
        "SD": {
            "Supplier_Diversification_Index": None,
            "Supply_Chain_Robustness_Index": None,
        },
        "ICR": {
            "Cash_Readiness_Index": None,
            "Runway_Buffer_Index": None,
        },
        "CFS": {
            "Revenue_Predictability_Index": None,
            "Revenue_Trajectory_Index": None,
        },
        "RQ": {
            "Receivables_Safety_Index": None,
            "Client_Payment_Discipline_Index": None,
        },
        "ICDL": {
            "Debt_Repayment_Discipline_Index": None,
            "Debt_Service_Coverage_Index": None,
            "Solvency_Leverage_Index": None,
        },
    }

    def __init__(self) -> None:
        self.submodules = [
            OwnershipStructureEvaluator(),
            WebReputationEvaluator(),
            MacroSectorRiskEvaluator(),
            ClientDependencyEvaluator(),
            SupplierDependencyEvaluator(),
            ImmediateCashReadinessEvaluator(),
            CashflowStabilityEvaluator(),
            ReceivablesQualityEvaluator(),
            CreditDisciplineLeverageEvaluator(),
        ]

    def run_analysis(
        self, snapshot: Any, as_of_date: date | None = None
    ) -> UnderwritingPipelineResult:
        """
        Executes all 9 submodules with per-submodule exception isolation,
        aggregates the canonical 18-element feature vector, and compiles the diagnostic dossier.
        """
        raw_bid = (
            getattr(snapshot, "business_id", None)
            or getattr(getattr(snapshot, "business", None), "business_id", None)
        )
        if raw_bid is None:
            business_id = UUID("00000000-0000-0000-0000-000000000000")
        elif isinstance(raw_bid, str):
            business_id = UUID(raw_bid)
        else:
            business_id = raw_bid

        if as_of_date is not None:
            cutoff_date = as_of_date.date() if isinstance(as_of_date, datetime) else as_of_date
        else:
            raw_snap_date = getattr(snapshot, "as_of_date", None)
            if raw_snap_date is not None:
                cutoff_date = (
                    raw_snap_date.date()
                    if isinstance(raw_snap_date, datetime)
                    else raw_snap_date
                )
            else:
                cutoff_date = date.today()

        results: dict[str, SubmoduleResult] = {}

        for sm in self.submodules:
            code = sm.submodule_code
            try:
                res = sm.evaluate(snapshot)
                results[res.submodule_code] = res
            except Exception as exc:
                logger.error(
                    "Submodule %s evaluation raised unexpected exception: %s",
                    code,
                    exc,
                    exc_info=True,
                )
                empty_indices = dict(self.SUBMODULE_EMPTY_INDICES.get(code, {}))
                results[code] = SubmoduleResult(
                    submodule_code=code,
                    status=EvaluationStatus.ERROR,
                    impact_weight=sm.impact_weight,
                    verdict="ERROR",
                    indices=empty_indices,
                    summary=f"Evaluation encountered error: {exc}",
                    diagnostic_report=(
                        f"[{code}]\n"
                        f"STATUS: ERROR\n"
                        f"VERDICT: ERROR\n"
                        f"ERROR: {exc}"
                    ),
                )

        # Construct 18-element feature vector strictly in canonical order
        os_res = results.get("OS")
        wpr_res = results.get("WPR")
        msr_res = results.get("MSR")
        cd_res = results.get("CD")
        sd_res = results.get("SD")
        icr_res = results.get("ICR")
        cfs_res = results.get("CFS")
        rq_res = results.get("RQ")
        icdl_res = results.get("ICDL")

        feature_vector: list[float | None] = [
            os_res.indices.get("Ownership_Dispersion_Index") if os_res else None,
            os_res.indices.get("Governance_Independence_Index") if os_res else None,
            wpr_res.indices.get("Legal_Cleanliness_Index") if wpr_res else None,
            wpr_res.indices.get("Public_Reputation_Index") if wpr_res else None,
            msr_res.indices.get("Sector_Vitality_Index") if msr_res else None,
            cd_res.indices.get("Client_Diversification_Index") if cd_res else None,
            cd_res.indices.get("Top_Client_Exposure_Index") if cd_res else None,
            sd_res.indices.get("Supplier_Diversification_Index") if sd_res else None,
            sd_res.indices.get("Supply_Chain_Robustness_Index") if sd_res else None,
            icr_res.indices.get("Cash_Readiness_Index") if icr_res else None,
            icr_res.indices.get("Runway_Buffer_Index") if icr_res else None,
            cfs_res.indices.get("Revenue_Predictability_Index") if cfs_res else None,
            cfs_res.indices.get("Revenue_Trajectory_Index") if cfs_res else None,
            rq_res.indices.get("Receivables_Safety_Index") if rq_res else None,
            rq_res.indices.get("Client_Payment_Discipline_Index") if rq_res else None,
            icdl_res.indices.get("Debt_Repayment_Discipline_Index") if icdl_res else None,
            icdl_res.indices.get("Debt_Service_Coverage_Index") if icdl_res else None,
            icdl_res.indices.get("Solvency_Leverage_Index") if icdl_res else None,
        ]

        assert len(feature_vector) == 18, (
            f"Expected exactly 18 elements in canonical feature vector, but got {len(feature_vector)}"
        )

        # Compile plain text diagnostic dossier from non-empty diagnostic reports
        dossier_sections = [
            res.diagnostic_report.strip()
            for res in results.values()
            if res.diagnostic_report and res.diagnostic_report.strip()
        ]
        compiled_dossier_text = "\n\n".join(dossier_sections)

        return UnderwritingPipelineResult(
            business_id=business_id,
            as_of_date=cutoff_date,
            feature_vector=feature_vector,
            submodule_results=results,
            compiled_dossier_text=compiled_dossier_text,
        )


def run_full_ml_analysis(
    snapshot: Any, as_of_date: date | None = None
) -> UnderwritingPipelineResult:
    """Convenience helper function to execute full pipeline analysis."""
    pipeline = UnderwritingAnalyticalPipeline()
    return pipeline.run_analysis(snapshot, as_of_date=as_of_date)


__all__ = [
    "UnderwritingAnalyticalPipeline",
    "UnderwritingPipelineResult",
    "run_full_ml_analysis",
]
