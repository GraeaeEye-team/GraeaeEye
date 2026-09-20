"""
Decoupled Pipeline Orchestration Worker for GraeaeEye Underwriting Engine.

Executes asynchronous ingestion and analytical underwriting workflows in the background:
1. Spools uploaded multipart files to temporary scratch storage.
2. Invokes IngestionPipeline to parse statements, collect external intel, and persist to DAL.
3. Records ingestion outcome into analysis_logs table.
4. Invokes UnderwritingAnalyticalPipeline to evaluate all 9 submodules and score enterprise.
5. Catches all exceptions, updates analysis_runs to FAILED, and logs errors (P10 safe).
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import tempfile
from typing import Any, List, Optional, Tuple
from uuid import UUID

try:
    from src.fintech_app.ingestion.pipeline import IngestionPipeline
    from src.fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline
except ModuleNotFoundError:
    from fintech_app.ingestion.pipeline import IngestionPipeline
    from fintech_app.ml.pipeline import UnderwritingAnalyticalPipeline

logger = logging.getLogger("fintech_app.api.orchestration")


async def execute_orchestration_worker(
    db: Any,
    run_id: UUID,
    business_id: UUID,
    company_name: str,
    tax_id: str,
    sector_code: str,
    files_data: List[Tuple[str, bytes]],
    active_submodules: Optional[List[str]] = None,
) -> None:
    """
    Asynchronous background worker executing ingestion and analytical evaluation.

    Guaranteed never to raise unhandled exceptions out to the FastAPI event loop.
    """
    logger.info(
        "Starting orchestration worker for run %s (company: '%s', business_id: %s)",
        run_id,
        company_name,
        business_id,
    )

    # Transition status to PROCESSING
    try:
        if db is not None and hasattr(db, "update_records_in_analysis_runs"):
            await db.update_records_in_analysis_runs(
                updates={"status": "PROCESSING"},
                run_id=run_id,
            )
    except Exception as exc:
        logger.warning("Failed to update status to PROCESSING for run %s: %s", run_id, exc)

    try:
        # 1. Spool uploaded bytes to temporary scratch directory (outside repo)
        with tempfile.TemporaryDirectory() as temp_dir:
            spooled_file_paths: List[str] = []
            for fname, fbytes in files_data:
                # Sanitize basename to prevent path traversal
                clean_name = os.path.basename(fname) or "ledger.csv"
                file_path = os.path.join(temp_dir, clean_name)
                with open(file_path, "wb") as f:
                    f.write(fbytes)
                spooled_file_paths.append(file_path)

            # 2. Execute Ingestion Pipeline
            ingestion = IngestionPipeline(db=db)
            metadata = {
                "business_id": business_id,
                "tax_id": tax_id,
                "company_name": company_name,
                "sector_code": sector_code,
            }

            logger.info("Executing IngestionPipeline for run %s with %d files", run_id, len(spooled_file_paths))
            ingestion_res = await ingestion.run(
                metadata=metadata,
                files=spooled_file_paths,
            )

        # 3. Log Ingestion telemetry outcome
        if db is not None and hasattr(db, "add_record_to_analysis_logs"):
            if ingestion_res.success:
                severity = "WARN" if ingestion_res.warnings else "INFO"
                msg = f"Ingestion completed: {ingestion_res.records_ingested} records ingested."
                if ingestion_res.warnings:
                    msg += f" Warnings: {'; '.join(ingestion_res.warnings)}"
            else:
                severity = "ERROR"
                msg = f"Ingestion failed: {ingestion_res.error or ingestion_res.message}"

            await db.add_record_to_analysis_logs(
                run_id=run_id,
                severity=severity,
                stage="INGESTION",
                message=msg,
            )

        if not ingestion_res.success:
            logger.error("Ingestion failed for run %s: %s", run_id, ingestion_res.error)
            if db is not None and hasattr(db, "update_records_in_analysis_runs"):
                await db.update_records_in_analysis_runs(
                    updates={
                        "status": "FAILED",
                        "failure_reason": ingestion_res.error or "Ingestion pipeline failure",
                        "completed_at": datetime.now(timezone.utc),
                    },
                    run_id=run_id,
                )
            return

        # 4. Execute Underwriting Analytical Pipeline
        logger.info("Invoking UnderwritingAnalyticalPipeline.run_analysis_from_db for run %s", run_id)
        ml_pipeline = UnderwritingAnalyticalPipeline()
        await ml_pipeline.run_analysis_from_db(
            db=db,
            business_id=business_id,
            run_id=run_id,
            active_submodules=active_submodules,
        )

        logger.info("Orchestration worker completed successfully for run %s", run_id)

    except Exception as exc:
        logger.exception("Critical error in orchestration worker for run %s: %s", run_id, exc)
        try:
            if db is not None:
                if hasattr(db, "update_records_in_analysis_runs"):
                    await db.update_records_in_analysis_runs(
                        updates={
                            "status": "FAILED",
                            "failure_reason": str(exc),
                            "completed_at": datetime.now(timezone.utc),
                        },
                        run_id=run_id,
                    )
                if hasattr(db, "add_record_to_analysis_logs"):
                    await db.add_record_to_analysis_logs(
                        run_id=run_id,
                        severity="ERROR",
                        stage="ERROR",
                        message=f"Pipeline execution failure: {exc}",
                    )
        except Exception as db_exc:
            logger.error("Failed to record failure in DB for run %s: %s", run_id, db_exc)


__all__ = ["execute_orchestration_worker"]
