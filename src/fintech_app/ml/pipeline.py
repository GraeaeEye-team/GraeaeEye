"""
Master Pipeline Orchestrator for the Underwriting Analytical Core.
Runs all 9 autonomous submodules concurrently against CompanyDataSnapshot,
builds the standardized 18-element feature vector, and compiles the diagnostic report dossier.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from fintech_app.ml.submodule_ownership import OwnershipStructureEvaluator, SubmoduleResult
from fintech_app.ml.submodule_reputation import WebReputationEvaluator
from fintech_app.ml.submodule_macro import MacroSectorRiskEvaluator
from fintech_app.ml.submodule_client_dep import ClientDependencyEvaluator
from fintech_app.ml.submodule_supplier_dep import SupplierDependencyEvaluator
from fintech_app.ml.submodule_cash_readiness import ImmediateCashReadinessEvaluator
from fintech_app.ml.submodule_cash_stability import CashflowStabilityEvaluator
from fintech_app.ml.submodule_receivables import ReceivablesQualityEvaluator
from fintech_app.ml.submodule_credit_discipline import CreditDisciplineLeverageEvaluator


@dataclass
class UnderwritingPipelineResult:
    """Result of the complete 9-submodule analytical pipeline run."""
    business_id: UUID
    as_of_date: date
    feature_vector: List[Optional[float]]  # Exactly 18 numerical indices in canonical order
    submodule_results: Dict[str, SubmoduleResult]
    compiled_dossier_text: str


class UnderwritingAnalyticalPipeline:
    """Orchestrates parallel execution of all 9 analytical submodules."""

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

    def run_analysis(self, snapshot: Any, as_of_date: Optional[date] = None) -> UnderwritingPipelineResult:
        """Executes all 9 submodules and aggregates feature vector and reports."""
        business_id = getattr(snapshot, "business_id", None) or getattr(getattr(snapshot, "business", None), "business_id", None)
        cutoff_date = as_of_date or getattr(snapshot, "as_of_date", date.today())

        results: Dict[str, SubmoduleResult] = {}
        for sm in self.submodules:
            res = sm.evaluate(snapshot)
            results[res.submodule_code] = res

        # Construct 18-element feature vector in exact canonical order
        os_res = results.get("OS")
        wpr_res = results.get("WPR")
        msr_res = results.get("MSR")
        cd_res = results.get("CD")
        sd_res = results.get("SD")
        icr_res = results.get("ICR")
        cfs_res = results.get("CFS")
        rq_res = results.get("RQ")
        icdl_res = results.get("ICDL")

        feature_vector: List[Optional[float]] = [
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

        # Compile plain text diagnostic dossier
        dossier_sections = [res.diagnostic_report for res in results.values()]
        compiled_dossier_text = "\n\n".join(dossier_sections)

        return UnderwritingPipelineResult(
            business_id=business_id,
            as_of_date=cutoff_date,
            feature_vector=feature_vector,
            submodule_results=results,
            compiled_dossier_text=compiled_dossier_text,
        )


def run_full_ml_analysis(snapshot: Any) -> UnderwritingPipelineResult:
    """Convenience helper function to execute full pipeline analysis."""
    pipeline = UnderwritingAnalyticalPipeline()
    return pipeline.run_analysis(snapshot)
