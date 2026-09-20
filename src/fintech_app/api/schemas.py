"""
Pydantic v2 schemas and API-layer Data Transfer Objects (DTOs).

Aligned with Web Interface & Orchestration Layer Technical Architecture & Specification v2.0.
Provides frozen contracts for endpoints, canonical 18D feature vector schemas,
Decimal monetary typing, SSE event schemas, and standardized P10 error envelopes.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fintech_app.shared.schemas.user_types import AnalysisStatus

# =====================================================================
# 1. STANDARDIZED ERROR ENVELOPE (Rule P10)
# =====================================================================


class ErrorResponse(BaseModel):
    """Standardized error envelope required for every API error path."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(..., description="Human-readable description of the error.")
    code: str = Field(..., description="Machine-readable application error code.")


# =====================================================================
# 2. DOMAIN ENUMS & CANONICAL INDEX DEFINITIONS
# =====================================================================


class VerdictCategory(StrEnum):
    """Top-level analytical verdict category."""

    PRIME_LOW_RISK = "PRIME_LOW_RISK"
    MODERATE_MONITORED = "MODERATE_MONITORED"
    HIGH_RISK_REJECT = "HIGH_RISK_REJECT"


class Recommendation(StrEnum):
    """Top-level credit decision recommendation."""

    APPROVED = "APPROVED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECTED = "REJECTED"


class LogSeverity(StrEnum):
    """Log severity levels for streaming telemetry."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class SubmoduleExecutionStatus(StrEnum):
    """Lifecycle status for submodule execution telemetry."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    BYPASSED = "BYPASSED"
    FAILED = "FAILED"
    DATA_ABSENT = "DATA_ABSENT"


# Canonical 18 index keys in exact ordered sequence (Spec v2.0 §2)
CANONICAL_18D_KEYS: List[str] = [
    "ownership_dispersion_index",
    "governance_independence_index",
    "legal_cleanliness_index",
    "public_reputation_index",
    "sector_vitality_index",
    "client_diversification_index",
    "top_client_exposure_index",
    "supplier_diversification_index",
    "supply_chain_robustness_index",
    "cash_readiness_index",
    "runway_buffer_index",
    "revenue_predictability_index",
    "revenue_trajectory_index",
    "receivables_safety_index",
    "client_payment_discipline_index",
    "debt_repayment_discipline_index",
    "debt_service_coverage_index",
    "solvency_leverage_index",
]


class FeatureVector(BaseModel):
    """Primary web contract: 18D numerical feature vector object with named keys."""

    model_config = ConfigDict(extra="forbid")

    ownership_dispersion_index: Optional[float] = None
    governance_independence_index: Optional[float] = None
    legal_cleanliness_index: Optional[float] = None
    public_reputation_index: Optional[float] = None
    sector_vitality_index: Optional[float] = None
    client_diversification_index: Optional[float] = None
    top_client_exposure_index: Optional[float] = None
    supplier_diversification_index: Optional[float] = None
    supply_chain_robustness_index: Optional[float] = None
    cash_readiness_index: Optional[float] = None
    runway_buffer_index: Optional[float] = None
    revenue_predictability_index: Optional[float] = None
    revenue_trajectory_index: Optional[float] = None
    receivables_safety_index: Optional[float] = None
    client_payment_discipline_index: Optional[float] = None
    debt_repayment_discipline_index: Optional[float] = None
    debt_service_coverage_index: Optional[float] = None
    solvency_leverage_index: Optional[float] = None


# =====================================================================
# 3. AUTHENTICATION SCHEMAS
# =====================================================================


class UserLoginRequest(BaseModel):
    """Credentials payload for login and token requests."""

    email: str = Field(..., examples=["analyst@graeae.eye"])
    password: str = Field(..., examples=["correct-horse-battery-staple"])


class UserRegisterRequest(BaseModel):
    """Registration payload for new users."""

    email: str = Field(..., examples=["analyst@graeae.eye"])
    password: str = Field(..., examples=["correct-horse-battery-staple"])
    full_name: str = Field(default="Analyst User", examples=["Alexander Hamilton"])


class UserResponse(BaseModel):
    """Public user profile response with session authentication metadata."""

    user_id: UUID
    email: str
    full_name: str
    role: str = "ANALYST"
    is_active: bool = True
    access_token: Optional[str] = Field(default=None, description="JWT session token for headless or bearer clients.")
    token_type: Optional[str] = Field(default="bearer", description="Token type schema.")


class CurrentUser(BaseModel):
    """Authenticated user context injected via dependencies."""

    user_id: UUID
    email: str
    full_name: str
    role: str = "ANALYST"


# =====================================================================
# 4. SSE STREAM TELEMETRY EVENT SCHEMAS (Spec v2.0 §4.3)
# =====================================================================


class PipelineStageChangedEvent(BaseModel):
    """Payload for PIPELINE_STAGE_CHANGED SSE event."""

    stage: str
    progress_percentage: int


class LogEmittedEvent(BaseModel):
    """Payload for LOG_EMITTED SSE event."""

    timestamp: str
    severity: LogSeverity
    stage: str
    message: str


class SubmoduleStatusUpdatedEvent(BaseModel):
    """Payload for SUBMODULE_STATUS_UPDATED SSE event."""

    submodule_id: str
    status: str
    verdict: str


class PipelineCompleteEvent(BaseModel):
    """Payload for PIPELINE_COMPLETE terminal SSE event."""

    run_id: str
    universal_score: float
    redirect_url: str


class PipelineFailedEvent(BaseModel):
    """Payload for PIPELINE_FAILED terminal SSE event."""

    run_id: str
    error: str


# =====================================================================
# 5. ANALYSIS PIPELINE & REPORT SCHEMAS
# =====================================================================


class AnalysisStartResponse(BaseModel):
    """Immediate acknowledgment response for an initiated analysis run."""

    run_id: UUID
    status: AnalysisStatus = AnalysisStatus.QUEUED


class SubmoduleReportCard(BaseModel):
    """Diagnostic card summarizing a single submodule's execution."""

    submodule_id: str = Field(..., description="Canonical long-form ID (e.g., OS_4_1)")
    name: str
    status: SubmoduleExecutionStatus = Field(..., description="Execution status: SUCCESS, BYPASSED, DATA_ABSENT")
    verdict: str
    impact_weight: float
    indices: Optional[Dict[str, Optional[float]]] = None
    dry_report: str


class LLMSynthesisSummary(BaseModel):
    """Synthesized narrative summary for executive review."""

    headline: str
    summary_markdown: str
    critical_flags: List[str] = Field(default_factory=list)
    positive_indicators: List[str] = Field(default_factory=list)


class AnalysisReportResponse(BaseModel):
    """Complete Underwriting Dossier matching Spec v2.0 §5.4."""

    run_id: UUID
    company_name: str
    tax_id: str
    sector_code: str
    status: AnalysisStatus
    execution_status: str = "COMPLETED"
    created_at: datetime
    completed_at: Optional[datetime] = None

    # Primary web contract: Object with 18 named keys (values float or null)
    feature_vector: FeatureVector = Field(
        ...,
        description="18D feature vector object with named keys matching Web Spec v2.0.",
    )

    # ML-pipeline contract: Ordered 18-element list in canonical sequence
    feature_vector_ordered: List[Optional[float]] = Field(
        ...,
        min_length=18,
        max_length=18,
        description="Canonical ordered 18D numerical feature vector.",
    )

    submodules: List[SubmoduleReportCard]
    universal_score: float = Field(..., ge=0.0, le=100.0)
    probability_of_default: float = Field(..., ge=0.0, le=1.0)
    verdict_category: VerdictCategory
    recommendation: Recommendation
    llm_synthesis: LLMSynthesisSummary
    llm_final_summary: str = Field(..., description="Prose markdown summary matching DB-column continuity.")

    # Monetary field strictly typed as Decimal (Rule P6)
    max_credit_limit_mdl: Decimal = Field(
        ...,
        description="Maximum recommended credit limit in Moldovan Leu (MDL).",
    )


class HealthResponse(BaseModel):
    """System health check response."""

    status: str
    mock_engine: bool
    db: str
