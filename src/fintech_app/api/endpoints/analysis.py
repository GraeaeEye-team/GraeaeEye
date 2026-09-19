"""
Analysis Pipeline Endpoints for the GraeaeEye API (Phase 1).

Exposes:
- POST /api/v1/analysis/start: Initiates pipeline execution (multipart/form-data)
- GET  /api/v1/analysis/stream/{run_id}: Real-time Server-Sent Events (SSE) telemetry
- GET  /api/v1/analysis/report/{run_id}: Final Underwriting Dossier report
- GET  /api/v1/health: System health and engine status
"""

import json
import logging
from typing import List, Optional
from uuid import UUID

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

from fintech_app.api.dependencies import get_current_user
from fintech_app.api.mock_provider import mock_analysis_provider
from fintech_app.api.schemas import (
    AnalysisReportResponse,
    AnalysisStartResponse,
    CurrentUser,
    ErrorResponse,
    HealthResponse,
)
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
    files: Optional[List[UploadFile]] = File(
        default=None, description="Uploaded CSV financial ledgers (max 5)"
    ),
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalysisStartResponse:
    """Queues an underwriting analysis run and dispatches the background task."""
    # File-count guard (executed BEFORE BackgroundTasks enqueue, None-safe)
    uploaded = files or []
    if len(uploaded) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Maximum of 5 CSV files allowed.",
                "code": "TOO_MANY_FILES",
            },
        )

    # Parse active_submodules JSON array
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

    file_names = [f.filename or "unknown.csv" for f in uploaded]

    # Create run in Phase 1 mock provider
    run_id = await mock_analysis_provider.create_run(
        company_name=company_name,
        tax_id=tax_id,
        sector_code=sector_code,
        active_submodules=submodules_list,
        file_names=file_names,
    )

    # Dispatch background simulation (Rule 1 & Rule P8)
    background_tasks.add_task(mock_analysis_provider.execute_simulation, run_id)

    return AnalysisStartResponse(run_id=run_id, status=AnalysisStatus.QUEUED)


@router.get(
    "/analysis/stream/{run_id}",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Server-Sent Events telemetry stream."},
        404: {"model": ErrorResponse, "description": "Run not found."},
    },
    summary="Real-time telemetry stream",
    description="Streams pipeline execution telemetry over Server-Sent Events (SSE).",
)
async def stream_analysis(run_id: UUID) -> StreamingResponse:
    """Streams SSE telemetry events for the requested analysis run."""
    run = await mock_analysis_provider.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Analysis run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
        )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(
        mock_analysis_provider.stream_telemetry(run_id),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get(
    "/analysis/report/{run_id}",
    response_model=AnalysisReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": AnalysisReportResponse, "description": "Underwriting Dossier report."},
        404: {"model": ErrorResponse, "description": "Run not found."},
        409: {"model": ErrorResponse, "description": "Run has not completed yet."},
    },
    summary="Retrieve underwriting report",
    description="Returns the comprehensive Underwriting Dossier with canonical 18D feature vector.",
)
async def get_report(run_id: UUID) -> AnalysisReportResponse:
    """Fetches the final Underwriting Dossier once execution is completed."""
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
async def health_check() -> HealthResponse:
    """Health check endpoint. Unauthenticated; guaranteed never to 500."""
    return HealthResponse(status="ok", mock_engine=True, db="mock")
