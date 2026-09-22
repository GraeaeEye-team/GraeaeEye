"""
Master Pipeline Orchestrator for the Underwriting Analytical Core.
Runs all 9 autonomous submodules concurrently against CompanyDataSnapshot,
builds the standardized 18-element feature vector, and compiles the diagnostic report dossier.
Provides asynchronous database-backed evaluation via CompanyDataLoader.
"""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
import math
import time
from typing import Any, Optional, Union
from uuid import UUID

from ..core.config import settings
from ..db.connection import Database
from .base import EvaluationStatus, SubmoduleResult
from .llm_client import LLMExecutor
from .loader import CompanyDataLoader
from .scoring import CreditScoringEngine, CreditScoringResult
from .submodule_ownership import OwnershipStructureEvaluator
from .submodule_reputation import WebReputationEvaluator
from .submodule_macro import MacroSectorRiskEvaluator
from .submodule_client_dep import ClientDependencyEvaluator
from .submodule_supplier_dep import SupplierDependencyEvaluator
from .submodule_cash_readiness import ImmediateCashReadinessEvaluator
from .submodule_cash_stability import CashflowStabilityEvaluator
from .submodule_receivables import ReceivablesQualityEvaluator
from .submodule_credit_discipline import CreditDisciplineLeverageEvaluator

logger: logging.Logger = logging.getLogger("smart_credit.ml")


@dataclass
class UnderwritingPipelineResult:
    """Result of the complete 9-submodule analytical pipeline run."""

    business_id: UUID
    as_of_date: date
    feature_vector: list[float | None]  # Exactly 18 numerical indices in canonical order
    submodule_results: dict[str, SubmoduleResult]
    compiled_dossier_text: str
    scoring_result: Optional[CreditScoringResult] = None

    @property
    def feature_vector_18d(self) -> list[float | None]:
        return self.feature_vector

    @property
    def universal_score(self) -> float:
        if self.scoring_result is not None:
            return float(self.scoring_result.investment_attractiveness_score)
        return 0.0


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
        self,
        snapshot: Any,
        as_of_date: date | None = None,
        active_submodules: Optional[list[str]] = None,
    ) -> UnderwritingPipelineResult:
        """
        Executes active submodules with per-submodule exception isolation,
        aggregates the canonical 18-element feature vector, and compiles the diagnostic dossier.
        """
        raw_bid = getattr(snapshot, "business_id", None) or getattr(
            getattr(snapshot, "business", None), "business_id", None
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
                cutoff_date = raw_snap_date.date() if isinstance(raw_snap_date, datetime) else raw_snap_date
            else:
                cutoff_date = date.today()

        results: dict[str, SubmoduleResult] = {}

        normalized_active = None
        if active_submodules is not None:
            normalized_active = set()
            for sm_code in active_submodules:
                sm_clean = str(sm_code).strip().upper()
                if sm_clean in ("CR", "ICR"):
                    normalized_active.add("ICR")
                elif sm_clean in ("DL", "ICDL"):
                    normalized_active.add("ICDL")
                else:
                    normalized_active.add(sm_clean)

        for sm in self.submodules:
            code = sm.submodule_code
            if normalized_active is not None and code not in normalized_active:
                empty_indices = dict(self.SUBMODULE_EMPTY_INDICES.get(code, {}))
                results[code] = SubmoduleResult(
                    submodule_code=code,
                    status=EvaluationStatus.DATA_ABSENT,
                    impact_weight=sm.impact_weight,
                    verdict="SKIPPED",
                    indices=empty_indices,
                    summary=f"Submodule {code} was disabled in active_submodules configuration.",
                    diagnostic_report=(
                        f"[{code}]\n"
                        f"STATUS: DATA_ABSENT\n"
                        f"VERDICT: SKIPPED\n"
                        f"NOTE: Submodule disabled by configuration."
                    ),
                )
                continue

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
                    diagnostic_report=(f"[{code}]\n" f"STATUS: ERROR\n" f"VERDICT: ERROR\n" f"ERROR: {exc}"),
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

        assert len(feature_vector) == 18, f"Expected 18 elements in feature vector, got {len(feature_vector)}"

        # Compile plain text diagnostic dossier from non-empty diagnostic reports
        dossier_sections = [
            res.diagnostic_report.strip()
            for res in results.values()
            if res.diagnostic_report and res.diagnostic_report.strip()
        ]
        compiled_dossier_text = "\n\n".join(dossier_sections)

        scoring_engine = CreditScoringEngine()
        scoring_result = scoring_engine.calculate_score(
            feature_vector=feature_vector,
            compiled_dossier_text=compiled_dossier_text,
        )

        return UnderwritingPipelineResult(
            business_id=business_id,
            as_of_date=cutoff_date,
            feature_vector=feature_vector,
            submodule_results=results,
            compiled_dossier_text=compiled_dossier_text,
            scoring_result=scoring_result,
        )

    async def run_analysis_from_db(
        self,
        db: Database,
        business_id: Optional[UUID] = None,
        as_of_date: Optional[date] = None,
        run_id: Optional[UUID] = None,
        active_submodules: Optional[list[str]] = None,
        tax_id: Optional[str] = None,
        executor: Optional[Union[str, LLMExecutor]] = None,
        timeout: Optional[float] = None,
        heartbeat_interval: Optional[float] = None,
        **kwargs: Any,
    ) -> UnderwritingPipelineResult:
        """
        Asynchronously loads the complete financial graph for the company from PostgreSQL,
        compiles the typed CompanyDataSnapshot, executes the analytical submodules,
        computes investment attractiveness scoring, and updates analysis_runs and logs.

        :param db: Active Database connection instance.
        :param business_id: UUID of the company to analyze.
        :param as_of_date: Optional cutoff evaluation date (defaults to date.today()).
        :param run_id: Optional analysis run UUID for real-time telemetry logging.
        :param active_submodules: Optional list of submodule codes to execute. If provided,
                                  omitted submodules are marked SKIPPED/DATA_ABSENT.
        :param tax_id: Optional tax identifier to resolve business_id if omitted.
        :param executor: Optional custom LLMExecutor callable or registered executor key.
        :param timeout: Optional override for LLM inference timeout in seconds (defaults to settings.llm_inference_timeout).
        :param heartbeat_interval: Optional interval in seconds for LLM heartbeat logs (defaults to settings.llm_heartbeat_interval).
        :return: UnderwritingPipelineResult containing feature vector and scoring result.
        """
        if business_id is None and tax_id is not None:
            biz_rep = await db.get_records_from_businesses(find_only_first=True, tax_id=str(tax_id))
            if biz_rep.success and biz_rep.data:
                rec = (
                    biz_rep.data
                    if isinstance(biz_rep.data, dict)
                    else (biz_rep.data[0] if isinstance(biz_rep.data, list) and biz_rep.data else None)
                )
                if rec and "business_id" in rec:
                    business_id = (
                        rec["business_id"] if isinstance(rec["business_id"], UUID) else UUID(str(rec["business_id"]))
                    )

        if business_id is None:
            raise ValueError("business_id or valid tax_id must be provided to run_analysis_from_db.")

        effective_date = as_of_date or date.today()
        is_run_registered = False

        if run_id is not None:
            # Check if run exists in analysis_runs before emitting logs to prevent FK violation
            check_rep = await db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
            if check_rep.success and check_rep.data:
                is_run_registered = True
                await db.update_records_in_analysis_runs(updates={"status": "PROCESSING"}, run_id=run_id)
                await db.add_record_to_analysis_logs(
                    run_id=run_id,
                    severity="INFO",
                    stage="DATA_LOAD",
                    message="Загрузка финансового графа предприятия из PostgreSQL",
                )

        try:
            loader = CompanyDataLoader(db)
            snapshot = await loader.load_snapshot(business_id=business_id, as_of_date=effective_date)

            if is_run_registered and run_id is not None:
                await db.add_record_to_analysis_logs(
                    run_id=run_id,
                    severity="INFO",
                    stage="ML_EVALUATION",
                    message="Запуск 9 аналитических субмодулей",
                )

            pipeline_result = self.run_analysis(
                snapshot=snapshot,
                as_of_date=effective_date,
                active_submodules=active_submodules,
            )

            if is_run_registered and run_id is not None:
                await db.add_record_to_analysis_logs(
                    run_id=run_id,
                    severity="INFO",
                    stage="SCORING",
                    message="Расчет итогового инвестиционного скоринга и вероятности дефолта",
                )

            # Invoke CreditScoringEngine with exactly two arguments
            scoring_engine = CreditScoringEngine()
            scoring_result = scoring_engine.calculate_score(
                feature_vector=pipeline_result.feature_vector,
                compiled_dossier_text=pipeline_result.compiled_dossier_text,
            )
            pipeline_result.scoring_result = scoring_result

            # Determine status: COMPLETED if all 9 SUCCESS, else DEGRADED if any DATA_ABSENT/ERROR
            has_incomplete = any(
                res.status != EvaluationStatus.SUCCESS for res in pipeline_result.submodule_results.values()
            )
            final_status = "DEGRADED" if has_incomplete else "COMPLETED"

            if is_run_registered and run_id is not None:
                # Sanitize raw_indices_payload: strip NaN and convert np.float64 to float or None
                raw_indices: dict[str, float | None] = {}
                for idx, feat_name in enumerate(CreditScoringEngine.FEATURE_NAMES):
                    val = pipeline_result.feature_vector[idx] if idx < len(pipeline_result.feature_vector) else None
                    if val is not None:
                        try:
                            f_val = float(val)
                            raw_indices[feat_name] = None if math.isnan(f_val) else f_val
                        except (ValueError, TypeError):
                            raw_indices[feat_name] = None
                    else:
                        raw_indices[feat_name] = None

                # Safely serialize submodules_reports converting EvaluationStatus to str
                sub_reports = [
                    {
                        "submodule_code": res.submodule_code,
                        "status": (res.status.value if hasattr(res.status, "value") else str(res.status)),
                        "impact_weight": float(res.impact_weight),
                        "verdict": str(res.verdict),
                        "indices": {
                            ik: (None if iv is None or math.isnan(float(iv)) else float(iv))
                            for ik, iv in res.indices.items()
                        },
                        "summary": str(res.summary),
                        "diagnostic_report": str(res.diagnostic_report),
                    }
                    for res in pipeline_result.submodule_results.values()
                ]

                # Resolve LLM provider and timeout configuration
                if executor is not None:
                    provider_tag = (
                        executor if isinstance(executor, str) else getattr(executor, "__name__", "custom_executor")
                    )
                else:
                    provider_tag = getattr(settings, "llm_provider", "auto")
                model_tag = getattr(settings, "llm_model", "gpt-4o-mini")
                effective_timeout = (
                    timeout if timeout is not None else getattr(settings, "llm_inference_timeout", 300.0)
                )
                hb_interval = (
                    heartbeat_interval
                    if heartbeat_interval is not None
                    else getattr(settings, "llm_heartbeat_interval", 10.0)
                )

                await db.add_record_to_analysis_logs(
                    run_id=run_id,
                    severity="INFO",
                    stage="LLM_SYNTHESIS",
                    message=f"[LLM_START] Запуск генерации меморандума через {provider_tag}:{model_tag}. Ожидание ответа...",
                )

                # Fault-tolerant background heartbeat worker
                start_llm_time = time.perf_counter()

                async def _heartbeat_worker():
                    elapsed = 0.0
                    while True:
                        await asyncio.sleep(hb_interval)
                        elapsed += hb_interval
                        try:
                            await db.add_record_to_analysis_logs(
                                run_id=run_id,
                                severity="INFO",
                                stage="LLM_SYNTHESIS",
                                message=(
                                    f"[LLM_HEARTBEAT] Локальная нейросеть обрабатывает финансовое досье "
                                    f"(прошло {int(elapsed)}с / лимит {int(effective_timeout)}с)..."
                                ),
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception as log_exc:
                            logger.debug("Heartbeat log write suppressed: %s", log_exc)

                heartbeat_task = asyncio.create_task(_heartbeat_worker())

                llm_summary = scoring_result.executive_summary
                synthesis_engine_tag = "fallback:template"
                try:
                    detailed_res = await scoring_engine.generate_detailed_llm_summary(
                        scoring_result,
                        executor=executor,
                        timeout=effective_timeout,
                    )
                    llm_summary = detailed_res.text
                    synthesis_engine_tag = detailed_res.synthesis_engine

                    if detailed_res.fallback_used and detailed_res.status != "LLM_INFERENCE_SUCCESS":
                        await db.add_record_to_analysis_logs(
                            run_id=run_id,
                            severity="WARN",
                            stage="LLM_SYNTHESIS",
                            message=(
                                f"LLM_FALLBACK_TRIGGERED: Neural inference unavailable "
                                f"({detailed_res.error_details}). Switched to structured fallback memorandum."
                            ),
                        )
                    elif detailed_res.fallback_used:
                        await db.add_record_to_analysis_logs(
                            run_id=run_id,
                            severity="INFO",
                            stage="LLM_SYNTHESIS",
                            message="[REPORT_BUILDER] Сформирован институциональный структурированный меморандум андеррайтера (не-ИИ режим по умолчанию).",
                        )
                    else:
                        total_sec = round(time.perf_counter() - start_llm_time, 2)
                        char_count = len(llm_summary) if llm_summary else 0
                        await db.add_record_to_analysis_logs(
                            run_id=run_id,
                            severity="INFO",
                            stage="LLM_SYNTHESIS",
                            message=f"[LLM_SUCCESS] Меморандум успешно сгенерирован нейросетью за {total_sec}с ({char_count} символов).",
                        )
                except Exception as llm_exc:
                    logger.warning("LLM synthesis encountered error (%s). Using fallback summary.", llm_exc)
                    await db.add_record_to_analysis_logs(
                        run_id=run_id,
                        severity="WARN",
                        stage="LLM_SYNTHESIS",
                        message=f"LLM_FALLBACK_TRIGGERED: Exception during LLM dispatch: {llm_exc}.",
                    )
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

                raw_indices["_synthesis_engine"] = synthesis_engine_tag

                # Update analysis_runs with complete dossier and metrics
                score_dec = Decimal(str(round(scoring_result.investment_attractiveness_score, 2)))
                await db.update_records_in_analysis_runs(
                    updates={
                        "status": final_status,
                        "universal_score": score_dec,
                        "verdict_category": scoring_result.verdict_category,
                        "recommendation": scoring_result.recommendation,
                        "llm_final_summary": llm_summary,
                        "raw_indices_payload": raw_indices,
                        "submodules_reports": sub_reports,
                        "completed_at": datetime.now(timezone.utc),
                    },
                    run_id=run_id,
                )

                await db.add_record_to_analysis_logs(
                    run_id=run_id,
                    severity="INFO",
                    stage="PIPELINE_COMPLETE",
                    message=(
                        f"Аналитический пайплайн завершен со статусом {final_status}. "
                        f"Скор: {scoring_result.investment_attractiveness_score:.1f}/100.0 "
                        f"({scoring_result.verdict_category})"
                    ),
                )

            return pipeline_result

        except Exception as exc:
            logger.error(
                "Pipeline execution failed for business %s (run_id: %s): %s",
                business_id,
                run_id,
                exc,
                exc_info=True,
            )
            if is_run_registered and run_id is not None:
                await db.update_records_in_analysis_runs(
                    updates={
                        "status": "FAILED",
                        "failure_reason": str(exc),
                        "completed_at": datetime.now(timezone.utc),
                    },
                    run_id=run_id,
                )
                await db.add_record_to_analysis_logs(
                    run_id=run_id,
                    severity="ERROR",
                    stage="ERROR",
                    message=f"Критическая ошибка выполнения пайплайна: {exc}",
                )
            raise exc


def run_full_ml_analysis(snapshot: Any, as_of_date: date | None = None) -> UnderwritingPipelineResult:
    """Convenience helper function to execute full pipeline analysis on a snapshot."""
    pipeline = UnderwritingAnalyticalPipeline()
    return pipeline.run_analysis(snapshot, as_of_date=as_of_date)


async def run_analysis_from_db(
    db: Optional[Database] = None,
    business_id: Optional[UUID] = None,
    as_of_date: Optional[date] = None,
    run_id: Optional[UUID] = None,
    active_submodules: Optional[list[str]] = None,
    tax_id: Optional[str] = None,
    **kwargs: Any,
) -> UnderwritingPipelineResult:
    """Convenience async helper to load data from database and execute full pipeline analysis."""
    if db is None:
        db = kwargs.get("db")
    if db is None:
        raise ValueError("db connection instance must be provided to run_analysis_from_db.")
    pipeline = UnderwritingAnalyticalPipeline()
    return await pipeline.run_analysis_from_db(
        db=db,
        business_id=business_id,
        as_of_date=as_of_date,
        run_id=run_id,
        active_submodules=active_submodules,
        tax_id=tax_id,
        **kwargs,
    )


__all__ = [
    "CompanyDataLoader",
    "UnderwritingAnalyticalPipeline",
    "UnderwritingPipelineResult",
    "run_analysis_from_db",
    "run_full_ml_analysis",
]
