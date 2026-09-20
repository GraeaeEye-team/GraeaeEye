"""
Analysis Pipeline Endpoints for the GraeaeEye API.

Exposes:
- POST /api/v1/analysis/start: Initiates pipeline execution (multipart/form-data)
- GET  /api/v1/analysis/stream/{run_id}: Real-time Server-Sent Events (SSE) telemetry
- GET  /api/v1/analysis/report/{run_id}: Final Underwriting Dossier report
- GET  /api/v1/health: System health and engine status
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import logging
import math
from typing import Any, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from fintech_app.api.contract_mapping import map_ml_result_to_analysis_report
from fintech_app.api.dependencies import get_current_user, get_db
from fintech_app.api.mock_provider import mock_analysis_provider
from fintech_app.api.orchestration import execute_orchestration_worker
from fintech_app.api.schemas import (
    AnalysisReportResponse,
    AnalysisStartResponse,
    CurrentUser,
    ErrorResponse,
    HealthResponse,
)
from fintech_app.api.stream_provider import stream_telemetry_from_db
from fintech_app.core.config import settings
from fintech_app.ml.base import EvaluationStatus, SubmoduleResult, clamp
from fintech_app.ml.pipeline import UnderwritingPipelineResult
from fintech_app.ml.scoring import CreditScoringEngine, CreditScoringResult
from fintech_app.shared.schemas.user_types import AnalysisStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/analysis/start",
    response_model=AnalysisStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"model": AnalysisStartResponse, "description": "Analysis pipeline queued."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        422: {"model": ErrorResponse, "description": "Validation error or too many files."},
        503: {"model": ErrorResponse, "description": "Database unavailable."},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": [
                            "company_name",
                            "tax_id",
                            "sector_code",
                            "active_submodules",
                        ],
                        "properties": {
                            "company_name": {
                                "type": "string",
                                "title": "Company Name",
                                "description": "Legal company name",
                            },
                            "tax_id": {
                                "type": "string",
                                "title": "Tax Id",
                                "description": "Tax identification number (IDNO)",
                            },
                            "sector_code": {
                                "type": "string",
                                "title": "Sector Code",
                                "description": "Industry sector code (NACE/CAEM)",
                            },
                            "active_submodules": {
                                "type": "string",
                                "title": "Active Submodules",
                                "description": (
                                    'JSON array of active submodule codes, e.g. ["OS","WPR","MSR","CD","SD","ICR","CFS","RQ","ICDL"]'
                                ),
                            },
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary",
                                },
                                "description": "Uploaded CSV financial ledgers (max 5)",
                            },
                        },
                    }
                }
            }
        }
    },
    summary="Start underwriting analysis",
    description="Accepts company details and up to 5 CSV documents to initiate scoring.",
)
async def start_analysis(
    background_tasks: BackgroundTasks,
    company_name: str = Form(..., description="Legal company name"),
    tax_id: str = Form(..., description="Tax identification number (IDNO)"),
    sector_code: str = Form(..., description="Industry sector code (NACE/CAEM)"),
    active_submodules: str = Form(
        ...,
        description='JSON array of active submodule codes, e.g. ["OS","WPR","MSR","CD","SD","ICR","CFS","RQ","ICDL"]',
    ),
    files: List[UploadFile] = File(
        ..., description="Uploaded CSV financial ledgers (max 5)"
    ),
    current_user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> AnalysisStartResponse:
    """Queues an underwriting analysis run and dispatches the background task."""
    # 1. File-count guard (executed BEFORE BackgroundTasks enqueue, None-safe)
    uploaded = files or []
    if len(uploaded) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Maximum of 5 CSV files allowed.",
                "code": "TOO_MANY_FILES",
            },
        )

    # 2. Parse active_submodules JSON array
    try:
        submodules_list = json.loads(active_submodules)
        if not isinstance(submodules_list, list):
            raise ValueError("Expected a JSON array of strings")
    except Exception as exc:
        logger.warning("Invalid active_submodules payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": f"Invalid active_submodules format: {exc}",
                "code": "VALIDATION_ERROR",
            },
        )

    # 3. Path Branching based on USE_MOCK_ENGINE
    if settings.use_mock_engine:
        file_names = [f.filename or "unknown.csv" for f in uploaded]
        run_id = await mock_analysis_provider.create_run(
            company_name=company_name,
            tax_id=tax_id,
            sector_code=sector_code,
            active_submodules=submodules_list,
            file_names=file_names,
        )
        background_tasks.add_task(mock_analysis_provider.execute_simulation, run_id)
        return AnalysisStartResponse(run_id=run_id, status=AnalysisStatus.QUEUED)

    # Real Orchestration Path
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Database service is currently unavailable.",
                "code": "DB_UNAVAILABLE",
            },
        )

    # Read uploaded file contents before background task dispatch
    files_data: List[tuple[str, bytes]] = []
    for f in uploaded:
        content = await f.read()
        files_data.append((f.filename or "ledger.csv", content))

    files_manifest = {
        "files": [{"filename": fname, "size": len(fbytes)} for fname, fbytes in files_data]
    }

    # Register enterprise record in businesses table
    biz_rep = await db.add_record_to_businesses(
        tax_id=tax_id,
        legal_name=company_name,
        industry_code=sector_code,
        registration_date=date.today(),
    )
    business_id = biz_rep.data.get("business_id") if (biz_rep.success and biz_rep.data) else uuid4()

    # Create run entry in analysis_runs
    run_id = uuid4()
    await db.add_record_to_analysis_runs(
        user_id=current_user.user_id,
        business_id=business_id,
        run_id=run_id,
        input_company_name=company_name,
        input_tax_id=tax_id,
        input_industry_code=sector_code,
        files_manifest=files_manifest,
        active_submodules=submodules_list,
        status="QUEUED",
    )

    # Dispatch background orchestration worker
    background_tasks.add_task(
        execute_orchestration_worker,
        db=db,
        run_id=run_id,
        business_id=business_id,
        company_name=company_name,
        tax_id=tax_id,
        sector_code=sector_code,
        files_data=files_data,
        active_submodules=submodules_list,
    )

    return AnalysisStartResponse(run_id=run_id, status=AnalysisStatus.QUEUED)


@router.get(
    "/analysis/stream/{run_id}",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Server-Sent Events telemetry stream."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Run not found."},
        503: {"model": ErrorResponse, "description": "Database unavailable."},
    },
    summary="Real-time telemetry stream",
    description="Streams pipeline execution telemetry over Server-Sent Events (SSE).",
)
async def stream_analysis(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> StreamingResponse:
    """Streams SSE telemetry events for the requested analysis run."""
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    if settings.use_mock_engine:
        run = await mock_analysis_provider.get_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Analysis run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
            )
        return StreamingResponse(
            mock_analysis_provider.stream_telemetry(run_id),
            media_type="text/event-stream",
            headers=headers,
        )

    # Real Path
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Database service is currently unavailable.",
                "code": "DB_UNAVAILABLE",
            },
        )

    run_rep = await db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
    if not run_rep.success or not run_rep.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Analysis run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
        )

    return StreamingResponse(
        stream_telemetry_from_db(db=db, run_id=run_id),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get(
    "/analysis/report/{run_id}",
    response_model=AnalysisReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": AnalysisReportResponse, "description": "Underwriting Dossier report."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Run not found."},
        409: {"model": ErrorResponse, "description": "Run has not completed yet."},
        503: {"model": ErrorResponse, "description": "Database unavailable."},
    },
    summary="Retrieve underwriting report",
    description="Returns the comprehensive Underwriting Dossier with canonical 18D feature vector.",
)
async def get_report(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> AnalysisReportResponse:
    """Fetches the final Underwriting Dossier once execution is completed."""
    if settings.use_mock_engine:
        run = await mock_analysis_provider.get_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Analysis run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
            )

        if run.status != AnalysisStatus.COMPLETED or run.report is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": f"Analysis run '{run_id}' has not completed yet (current status: {run.status.value}).",
                    "code": "RUN_NOT_READY",
                },
            )
        return run.report

    # Real Path
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Database service is currently unavailable.",
                "code": "DB_UNAVAILABLE",
            },
        )

    run_rep = await db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
    if not run_rep.success or not run_rep.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Analysis run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
        )

    run_row = run_rep.data
    run_status = str(run_row.get("status", "PROCESSING"))

    if run_status not in ("COMPLETED", "DEGRADED"):
        msg = (
            f"Analysis run '{run_id}' has not completed yet (current status: {run_status})."
            if run_status != "FAILED"
            else f"Analysis run '{run_id}' failed: {run_row.get('failure_reason')}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": msg,
                "code": "RUN_NOT_READY",
            },
        )

    # Reconstruct UnderwritingPipelineResult from database records
    raw_indices = run_row.get("raw_indices_payload") or {}
    sub_reports = run_row.get("submodules_reports") or []

    sub_results_dict: dict[str, SubmoduleResult] = {}
    for sr in sub_reports:
        code = str(sr.get("submodule_code") or "")
        st_str = str(sr.get("status", "SUCCESS"))
        if st_str == "DATA_ABSENT":
            eval_st = EvaluationStatus.DATA_ABSENT
        elif st_str == "ERROR":
            eval_st = EvaluationStatus.ERROR
        else:
            eval_st = EvaluationStatus.SUCCESS

        sub_results_dict[code] = SubmoduleResult(
            submodule_code=code,
            status=eval_st,
            impact_weight=float(sr.get("impact_weight") or 0.0),
            verdict=str(sr.get("verdict") or "OPTIMAL"),
            indices=sr.get("indices") or {},
            summary=str(sr.get("summary") or ""),
            diagnostic_report=str(sr.get("diagnostic_report") or ""),
        )

    ordered_fv: List[Optional[float]] = []
    for feat_name in CreditScoringEngine.FEATURE_NAMES:
        val = raw_indices.get(feat_name)
        if val is None:
            val = raw_indices.get(feat_name.lower())
        ordered_fv.append(float(val) if val is not None else None)

    score_val = float(run_row.get("universal_score") or 50.0)
    try:
        pd_val = round(clamp(1.0 / (1.0 + math.exp((score_val - 50.0) / 12.0)), 0.001, 0.999), 4)
    except OverflowError:
        pd_val = 0.001 if score_val > 50.0 else 0.999

    scoring_result = CreditScoringResult(
        investment_attractiveness_score=score_val,
        probability_of_default=pd_val,
        verdict_category=str(run_row.get("verdict_category") or "MODERATE_MONITORED"),
        recommendation=str(run_row.get("recommendation") or "MANUAL_REVIEW"),
        executive_summary=str(run_row.get("llm_final_summary") or ""),
    )

    biz_id = run_row.get("business_id") or uuid4()
    comp_at = run_row.get("completed_at")
    as_of = comp_at.date() if isinstance(comp_at, datetime) else date.today()

    pipeline_res = UnderwritingPipelineResult(
        business_id=biz_id,
        as_of_date=as_of,
        feature_vector=ordered_fv,
        submodule_results=sub_results_dict,
        compiled_dossier_text=run_row.get("llm_final_summary") or "",
        scoring_result=scoring_result,
    )

    created_at = run_row.get("created_at") or datetime.now(timezone.utc)
    completed_at = run_row.get("completed_at") or datetime.now(timezone.utc)

    return map_ml_result_to_analysis_report(
        pipeline_result=pipeline_res,
        run_id=run_id,
        company_name=str(run_row.get("input_company_name") or "Evaluated Enterprise"),
        tax_id=str(run_row.get("input_tax_id") or "0000000000000"),
        sector_code=str(run_row.get("input_industry_code") or "0000"),
        created_at=created_at,
        completed_at=completed_at,
        max_credit_limit_mdl=Decimal("1250000.00"),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": HealthResponse, "description": "Service health status."},
    },
    summary="System health check",
    description="Returns service availability and status of mock and database subsystems.",
)
async def health_check(db: Any = Depends(get_db)) -> HealthResponse:
    """Health check endpoint. Unauthenticated; guaranteed never to 500."""
    if settings.use_mock_engine:
        return HealthResponse(status="ok", mock_engine=True, db="mock")

    db_status = "connected" if db is not None else "unavailable"
    return HealthResponse(status="ok", mock_engine=False, db=db_status)
