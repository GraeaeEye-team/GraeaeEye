"""
Mock Analysis Provider for Smart Credit System (Phase 1).

Aligned with Web Interface & Orchestration Layer Technical Architecture & Specification v2.0.
Simulates deterministic asynchronous pipeline runs (~8 seconds), emits 5 typed SSE events
with standard framing, implements file-driven submodule bypass logic, handles deterministic failure
path, and generates complete Underwriting Dossiers matching the v2.0 contract.

MOCK-ONLY: This in-process store and synthetic execution engine exist solely for Phase 1
to unblock UI integration. Phase 2 replaces this module with real PostgreSQL persistence
and background workers (Rule 1 & Rule 2).
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
import os
import random
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from .schemas import (
    CANONICAL_18D_KEYS,
    AnalysisReportResponse,
    FeatureVector,
    LLMSynthesisSummary,
    LogSeverity,
    Recommendation,
    SubmoduleExecutionStatus,
    SubmoduleReportCard,
    VerdictCategory,
)
from ..shared.schemas.user_types import AnalysisStatus

logger = logging.getLogger(__name__)

# Configuration flag (default true in Phase 1)
USE_MOCK_ENGINE: bool = os.getenv("USE_MOCK_ENGINE", "true").lower() in ("true", "1", "yes")

# Canonical Submodule Specification (Spec v2.0 §2 & §5.2)
SUBMODULE_METADATA = [
    {
        "id": "OS_4_1",
        "short": "OS",
        "name": "Ownership Structure",
        "weight": 0.08,
        "file": "shareholders.csv",
        "indices": ["ownership_dispersion_index", "governance_independence_index"],
        "default_indices": {"ownership_dispersion_index": 65.0, "governance_independence_index": 45.0},
        "verdict": "CONCENTRATED_OWNERSHIP",
        "summary": "High equity concentration in founding executive team.",
    },
    {
        "id": "WPR_4_2",
        "short": "WPR",
        "name": "Web Presence & Legal Reputation",
        "weight": 0.12,
        "file": None,
        "indices": ["legal_cleanliness_index", "public_reputation_index"],
        "default_indices": {"legal_cleanliness_index": 92.0, "public_reputation_index": 80.0},
        "verdict": "LEGAL_INTEGRITY_CONFIRMED",
        "summary": "Clean judicial registry, zero sanctions, positive sentiment.",
    },
    {
        "id": "MSR_4_3",
        "short": "MSR",
        "name": "Macro & Sector Risk",
        "weight": 0.05,
        "file": None,
        "indices": ["sector_vitality_index"],
        "default_indices": {"sector_vitality_index": 71.5},
        "verdict": "STABLE_SECTOR",
        "summary": "Operating sector exhibits steady YoY expansion.",
    },
    {
        "id": "CD_4_4",
        "short": "CD",
        "name": "Client Dependency",
        "weight": 0.10,
        "file": "invoices.csv",
        "indices": ["client_diversification_index", "top_client_exposure_index"],
        "default_indices": {"client_diversification_index": 48.0, "top_client_exposure_index": 52.0},
        "verdict": "MODERATE_CONCENTRATION",
        "summary": "Top client accounts for over 45% of gross invoice volume.",
    },
    {
        "id": "SD_4_5",
        "short": "SD",
        "name": "Supplier Dependency",
        "weight": 0.08,
        "file": "invoices.csv",
        "indices": ["supplier_diversification_index", "supply_chain_robustness_index"],
        "default_indices": {"supplier_diversification_index": 84.0, "supply_chain_robustness_index": 76.0},
        "verdict": "DIVERSIFIED_SUPPLY_CHAIN",
        "summary": "Procurement distributed across multiple established vendors.",
    },
    {
        "id": "ICR_4_6",
        "short": "ICR",
        "name": "Immediate Cash Readiness",
        "weight": 0.15,
        "file": "accounts.csv",
        "indices": ["cash_readiness_index", "runway_buffer_index"],
        "default_indices": {"cash_readiness_index": 82.5, "runway_buffer_index": 75.0},
        "verdict": "LIQUID_AND_SOLVENT",
        "summary": "Solid liquidity cushion with over 40 days operational runway.",
    },
    {
        "id": "CFS_4_7",
        "short": "CFS",
        "name": "Cash Flow Stability",
        "weight": 0.08,
        "file": "transactions.csv",
        "indices": ["revenue_predictability_index", "revenue_trajectory_index"],
        "default_indices": {"revenue_predictability_index": 88.0, "revenue_trajectory_index": 62.0},
        "verdict": "CONSISTENT_FLOWS",
        "summary": "Consistent monthly revenue inflows with predictable seasonality.",
    },
    {
        "id": "RQ_4_8",
        "short": "RQ",
        "name": "Receivables Quality",
        "weight": 0.14,
        "file": "invoices.csv",
        "indices": ["receivables_safety_index", "client_payment_discipline_index"],
        "default_indices": {"receivables_safety_index": 70.0, "client_payment_discipline_index": 64.0},
        "verdict": "PROMPT_COLLECTIONS",
        "summary": "Historical invoices settled within 14 days of contractual due date.",
    },
    {
        "id": "ICDL_4_9",
        "short": "ICDL",
        "name": "Internal Credit Discipline & Leverage",
        "weight": 0.16,
        "file": "obligations.csv",
        "indices": [
            "debt_repayment_discipline_index",
            "debt_service_coverage_index",
            "solvency_leverage_index",
        ],
        "default_indices": {
            "debt_repayment_discipline_index": 95.0,
            "debt_service_coverage_index": 85.0,
            "solvency_leverage_index": 77.0,
        },
        "verdict": "PRIME_CREDIT",
        "summary": "Credit facilities servicing verified without delinquency.",
    },
]


@dataclass
class MockRunState:
    """In-memory representation of a mock analysis execution session."""

    run_id: UUID
    company_name: str
    tax_id: str
    sector_code: str
    active_submodules: List[str]
    file_names: List[str]
    user_id: Optional[UUID] = None
    status: AnalysisStatus = AnalysisStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    # List of (event_type, payload_dict)
    events: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    report: Optional[AnalysisReportResponse] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MockAnalysisProvider:
    """
    Deterministic mock engine simulating pipeline execution and SSE telemetry streaming.

    Fully aligned with Web Interface Specification v2.0.
    """

    def __init__(self) -> None:
        self._runs: Dict[UUID, MockRunState] = {}
        self._store_lock = asyncio.Lock()

    async def create_run(
        self,
        company_name: str,
        tax_id: str,
        sector_code: str,
        active_submodules: List[str],
        file_names: List[str],
        user_id: Optional[UUID] = None,
    ) -> UUID:
        """Initializes a new mock analysis run in QUEUED state."""
        run_id = uuid4()
        run_state = MockRunState(
            run_id=run_id,
            company_name=company_name,
            tax_id=tax_id,
            sector_code=sector_code,
            active_submodules=active_submodules,
            file_names=file_names,
            user_id=user_id,
            status=AnalysisStatus.QUEUED,
        )
        async with self._store_lock:
            self._runs[run_id] = run_state
        logger.info("MockAnalysisProvider: Created mock run %s for company '%s'", run_id, company_name)
        return run_id

    async def get_run(self, run_id: UUID) -> Optional[MockRunState]:
        """Retrieves a mock run state by run_id."""
        async with self._store_lock:
            return self._runs.get(run_id)

    async def get_user_runs(
        self,
        user_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[MockRunState], int]:
        """Retrieves runs associated with user_id, or all if user_id is None (admin)."""
        async with self._store_lock:
            all_runs = list(self._runs.values())

        if user_id is not None:
            filtered = [r for r in all_runs if r.user_id == user_id]
        else:
            filtered = all_runs

        filtered.sort(key=lambda r: r.created_at, reverse=True)
        total = len(filtered)
        paginated = filtered[offset : offset + limit]
        return paginated, total

    async def execute_simulation(self, run_id: UUID) -> None:
        """
        Executes deterministic pipeline simulation with timing profile per Spec v2.0 §5.3:
        1.0 s ingestion, 1.5 s graph, 0.4 s per active submodule, 0.2 s per bypassed, 2.0 s LLM.
        Total run time: ~6-10 seconds.
        """
        run = await self.get_run(run_id)
        if not run:
            logger.error("MockAnalysisProvider: Run %s not found for simulation", run_id)
            return

        run.status = AnalysisStatus.PROCESSING
        seed_key = f"{run.company_name}:{run.tax_id}:{run.sector_code}"
        seed_val = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed_val)

        # Deterministic failure path check (Requirement 5):
        # Any uploaded filename containing "invalid" (case-insensitive) or non-.csv extension
        bad_file = None
        for fn in run.file_names:
            fn_lower = fn.lower()
            if "invalid" in fn_lower or not fn_lower.endswith(".csv"):
                bad_file = fn
                break

        if bad_file:
            # Simulate parsing stage before emitting failure
            await asyncio.sleep(1.0)
            now_iso = datetime.now(timezone.utc).isoformat()
            stage_event = ("PIPELINE_STAGE_CHANGED", {"stage": "PARSING", "progress_percentage": 10})
            log_event = (
                "LOG_EMITTED",
                {
                    "timestamp": now_iso,
                    "severity": "ERROR",
                    "stage": "PARSING",
                    "message": f"Validation failed for input document: {bad_file}. Invalid CSV schema.",
                },
            )
            fail_event = (
                "PIPELINE_FAILED",
                {
                    "run_id": str(run_id),
                    "error": f"Invalid CSV Schema in {bad_file}: missing required headers or non-CSV format",
                },
            )
            async with run.lock:
                run.events.extend([stage_event, log_event, fail_event])
                run.status = AnalysisStatus.FAILED
                run.completed_at = datetime.now(timezone.utc)
            logger.warning("MockAnalysisProvider: Run %s failed due to invalid file '%s'", run_id, bad_file)
            return

        # Stage 1: Ingestion (1.0 s)
        now_iso = datetime.now(timezone.utc).isoformat()
        async with run.lock:
            run.events.append(("PIPELINE_STAGE_CHANGED", {"stage": "INGESTION", "progress_percentage": 10}))
            run.events.append(
                (
                    "LOG_EMITTED",
                    {
                        "timestamp": now_iso,
                        "severity": "INFO",
                        "stage": "INGESTION",
                        "message": f"Parsing {len(run.file_names)} uploaded documents into relational ledger graph.",
                    },
                )
            )
        await asyncio.sleep(1.0)

        # Stage 2: Graph Assembly (1.5 s)
        now_iso = datetime.now(timezone.utc).isoformat()
        async with run.lock:
            run.events.append(("PIPELINE_STAGE_CHANGED", {"stage": "SNAPSHOT_ASSEMBLY", "progress_percentage": 25}))
            run.events.append(
                (
                    "LOG_EMITTED",
                    {
                        "timestamp": now_iso,
                        "severity": "INFO",
                        "stage": "SNAPSHOT_ASSEMBLY",
                        "message": f"Assembled CompanyDataSnapshot for Tax ID {run.tax_id}. Invariants verified.",
                    },
                )
            )
        await asyncio.sleep(1.5)

        # Stage 3: Submodule Execution (0.4 s active, 0.2 s bypassed)
        async with run.lock:
            run.events.append(("PIPELINE_STAGE_CHANGED", {"stage": "PROCESSING_SUBMODULES", "progress_percentage": 30}))

        active_submodules_input = [s.strip() for s in run.active_submodules if s.strip()]
        # Empty array means all enabled
        all_enabled = len(active_submodules_input) == 0

        submodule_results = {}
        for sm in SUBMODULE_METADATA:
            sm_id = sm["id"]
            short_code = sm["short"]
            req_file = sm["file"]

            is_selected = all_enabled or (sm_id in active_submodules_input) or (short_code in active_submodules_input)
            has_file = (req_file is None) or any(
                f.lower() == req_file.lower()
                or f.lower().endswith("/" + req_file.lower())
                or f.lower().endswith("\\" + req_file.lower())
                for f in run.file_names
            )

            is_active = is_selected and has_file
            submodule_results[sm_id] = is_active

            now_iso = datetime.now(timezone.utc).isoformat()
            if is_active:
                await asyncio.sleep(0.4)
                status_event = (
                    "SUBMODULE_STATUS_UPDATED",
                    {"submodule_id": sm_id, "status": "SUCCESS", "verdict": sm["verdict"]},
                )
                log_event = (
                    "LOG_EMITTED",
                    {
                        "timestamp": now_iso,
                        "severity": "INFO",
                        "stage": sm_id,
                        "message": f"Submodule {sm_id} ({sm['name']}): Evaluation completed with verdict {sm['verdict']}.",
                    },
                )
            else:
                await asyncio.sleep(0.2)
                status_event = (
                    "SUBMODULE_STATUS_UPDATED",
                    {"submodule_id": sm_id, "status": "BYPASSED", "verdict": "DATA_ABSENT"},
                )
                log_event = (
                    "LOG_EMITTED",
                    {
                        "timestamp": now_iso,
                        "severity": "WARN",
                        "stage": sm_id,
                        "message": f"Required data omitted ({req_file or 'deselected'}). Submodule {sm_id} BYPASSED.",
                    },
                )

            async with run.lock:
                run.events.append(status_event)
                run.events.append(log_event)

        # Stage 4: LLM Synthesis (2.0 s)
        now_iso = datetime.now(timezone.utc).isoformat()
        async with run.lock:
            run.events.append(("PIPELINE_STAGE_CHANGED", {"stage": "LLM_SYNTHESIS", "progress_percentage": 90}))
            run.events.append(
                (
                    "LOG_EMITTED",
                    {
                        "timestamp": now_iso,
                        "severity": "INFO",
                        "stage": "LLM_SYNTHESIS",
                        "message": "Streaming inference from Narrative Synthesizer...",
                    },
                )
            )
        await asyncio.sleep(2.0)

        # Stage 5: Terminal PIPELINE_COMPLETE
        async with run.lock:
            run.completed_at = datetime.now(timezone.utc)
            run.status = AnalysisStatus.COMPLETED
            report = self._build_deterministic_report(run, rng, submodule_results)
            run.report = report
            complete_event = (
                "PIPELINE_COMPLETE",
                {
                    "run_id": str(run_id),
                    "universal_score": report.universal_score,
                    "redirect_url": f"/analyze/report/{run_id}",
                },
            )
            run.events.append(complete_event)

        logger.info("MockAnalysisProvider: Run %s finished successfully", run_id)

    def _build_deterministic_report(
        self, run: MockRunState, rng: random.Random, submodule_active_map: Dict[str, bool]
    ) -> AnalysisReportResponse:
        """Constructs a schema-valid Underwriting Dossier conforming to Spec v2.0 §5.4."""
        feature_dict: Dict[str, Optional[float]] = {}
        submodule_cards: List[SubmoduleReportCard] = []

        for sm in SUBMODULE_METADATA:
            sm_id = sm["id"]
            is_active = submodule_active_map.get(sm_id, False)

            if is_active:
                sm_indices = {}
                for idx_key, base_val in sm["default_indices"].items():
                    val = round(base_val + rng.uniform(-2.0, 2.0), 1)
                    val = max(0.0, min(100.0, val))
                    sm_indices[idx_key] = val
                    feature_dict[idx_key] = val

                summary_text = sm["summary"]
                diagnostic_text = (
                    f"[{sm_id}: {sm['name'].upper()}]\n"
                    f"STATUS: SUCCESS\n"
                    f"VERDICT: {sm['verdict']}\n"
                    f"IMPACT WEIGHT: {sm['weight']:.2f}\n"
                    f"INDICES: " + ", ".join(f"{k}={v}" for k, v in sm_indices.items()) + "\n"
                    f"SUMMARY: {summary_text}"
                )
                card = SubmoduleReportCard(
                    submodule_id=sm_id,
                    name=sm["name"],
                    status="SUCCESS",
                    verdict=sm["verdict"],
                    impact_weight=sm["weight"],
                    indices=sm_indices,
                    dry_report=diagnostic_text,
                )
            else:
                sm_indices = {idx_key: None for idx_key in sm["indices"]}
                for idx_key in sm["indices"]:
                    feature_dict[idx_key] = None

                diagnostic_text = (
                    f"[{sm_id}: {sm['name'].upper()}]\n"
                    f"STATUS: DATA_ABSENT\n"
                    f"VERDICT: BYPASSED\n"
                    f"IMPACT WEIGHT: {sm['weight']:.2f}\n"
                    f"SUMMARY: Required input file ({sm['file'] or 'active toggle'}) omitted. Submodule bypassed in degraded mode."
                )
                card = SubmoduleReportCard(
                    submodule_id=sm_id,
                    name=sm["name"],
                    status=SubmoduleExecutionStatus.BYPASSED,
                    verdict="DATA_ABSENT",
                    impact_weight=sm["weight"],
                    indices=sm_indices,
                    dry_report=diagnostic_text,
                )

            submodule_cards.append(card)

        # Primary web contract: FeatureVector object with exact 18 keys
        feature_vector_obj = FeatureVector(**feature_dict)

        # ML-pipeline contract: List of 18 floats/None in canonical sequence
        feature_vector_ordered = [feature_dict[k] for k in CANONICAL_18D_KEYS]

        # Calculate universal score from active indices
        active_scores = [v for v in feature_vector_ordered if v is not None]
        if active_scores:
            universal_score = round(sum(active_scores) / len(active_scores), 2)
        else:
            universal_score = 50.0

        probability_of_default = round(max(0.005, min(0.95, (100.0 - universal_score) / 100.0)), 4)

        if universal_score >= 75.0:
            verdict_cat = VerdictCategory.PRIME_LOW_RISK
            rec = Recommendation.APPROVED
        elif universal_score >= 55.0:
            verdict_cat = VerdictCategory.MODERATE_MONITORED
            rec = Recommendation.MANUAL_REVIEW
        else:
            verdict_cat = VerdictCategory.HIGH_RISK_REJECT
            rec = Recommendation.REJECTED

        summary_markdown = (
            f"The enterprise **{run.company_name}** exhibits **robust operating cash flow** and strong "
            "baseline liquidity, maintaining approximately 45 days of operational runway. Debt servicing "
            "discipline remains exemplary with zero 90-day defaults. However, the business is structurally "
            "vulnerable to **client revenue concentration**: the top client accounts for 48% of annual B2B "
            "receivables, introducing severe cash gap vulnerability if contractual settlements slip past 30 days."
        )

        llm_synthesis = LLMSynthesisSummary(
            headline="Financially resilient enterprise with isolated counterparty concentration risk.",
            summary_markdown=summary_markdown,
            critical_flags=[
                "Top customer represents 48% of total gross receivables.",
                "Board governance lacks independent non-executive directors.",
            ],
            positive_indicators=[
                "Cash Ratio is 1.65, comfortably covering short-term operational liabilities.",
                "Debt Service Coverage Ratio (DSCR) is sustained at 2.1x.",
            ],
        )

        max_credit_limit = Decimal("1250000.00")

        return AnalysisReportResponse(
            run_id=run.run_id,
            company_name=run.company_name,
            tax_id=run.tax_id,
            sector_code=run.sector_code,
            status=run.status,
            execution_status="COMPLETED",
            created_at=run.created_at,
            completed_at=run.completed_at or datetime.now(timezone.utc),
            feature_vector=feature_vector_obj,
            feature_vector_ordered=feature_vector_ordered,
            submodules=submodule_cards,
            universal_score=universal_score,
            probability_of_default=probability_of_default,
            verdict_category=verdict_cat,
            recommendation=rec,
            llm_synthesis=llm_synthesis,
            llm_final_summary=summary_markdown,
            max_credit_limit_mdl=max_credit_limit,
        )

    async def stream_telemetry(self, run_id: UUID) -> AsyncGenerator[str, None]:
        """
        Streams telemetry in standard Server-Sent Events (SSE) framing:
        event: <TYPE>\\ndata: <JSON>\\n\\n
        """
        run = await self.get_run(run_id)
        if not run:
            logger.warning("MockAnalysisProvider: Stream requested for non-existent run %s", run_id)
            return

        cursor = 0
        try:
            while True:
                events_to_emit = []
                async with run.lock:
                    total_events = len(run.events)
                    if cursor < total_events:
                        events_to_emit = run.events[cursor:]
                        cursor = total_events
                    current_status = run.status

                for event_type, payload_dict in events_to_emit:
                    json_str = json.dumps(payload_dict)
                    yield f"event: {event_type}\ndata: {json_str}\n\n"

                if current_status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
                    break

                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("MockAnalysisProvider: SSE client disconnected for run %s", run_id)
            raise


# Global singleton instance for Phase 1
mock_analysis_provider = MockAnalysisProvider()
