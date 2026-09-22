"""
Real Server-Sent Events (SSE) Stream Provider backed by PostgreSQL / MockDatabase.

Streams pipeline execution telemetry by polling analysis_logs and analysis_runs:
- PIPELINE_STAGE_CHANGED when stages transition.
- LOG_EMITTED per analysis_logs record.
- SUBMODULE_STATUS_UPDATED per submodule report card (with canonical long IDs via contract_mapping).
- Terminal PIPELINE_COMPLETE or PIPELINE_FAILED when execution completes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, AsyncGenerator, Dict, Set
from uuid import UUID

from ..core.config import settings
from .contract_mapping import ml_submodule_to_api

logger = logging.getLogger("fintech_app.api.stream_provider")

STAGE_PROGRESS_MAP: Dict[str, int] = {
    "QUEUED": 5,
    "INGESTION": 15,
    "DATA_LOAD": 30,
    "ML_EVALUATION": 60,
    "SCORING": 80,
    "LLM_SYNTHESIS": 90,
    "PIPELINE_COMPLETE": 100,
    "COMPLETED": 100,
    "DEGRADED": 100,
}


async def stream_telemetry_from_db(
    db: Any,
    run_id: UUID,
) -> AsyncGenerator[str, None]:
    """
    Asynchronous generator yielding SSE telemetry frames from database tables.

    Polling cadence: ~200ms per iteration.
    Features:
    - Idle-reset timeout: each new log/heartbeat resets the inactivity counter.
    - Extended guard buffer: settings.llm_inference_timeout + 60.0 seconds.
    - Guarantees exact framing:
        event: <EVENT_NAME>\ndata: <JSON>\n\n
    """
    last_log_id: int = 0
    emitted_stages: Set[str] = set()

    cadence_sec: float = 0.20
    # Guard buffer: at least +60 seconds beyond LLM inference timeout
    timeout_guard_sec: float = getattr(settings, "llm_inference_timeout", 300.0) + 60.0
    max_idle_iterations: int = int(timeout_guard_sec / cadence_sec)
    idle_iterations: int = 0

    try:
        while idle_iterations < max_idle_iterations:
            idle_iterations += 1
            # 1. Fetch new logs from analysis_logs
            logs_rep = await db.get_records_from_analysis_logs(run_id=run_id)
            if logs_rep.success and logs_rep.data:
                # Filter rows newer than last_log_id and sort chronologically
                all_logs = logs_rep.data
                new_logs = [row for row in all_logs if row.get("log_id", 0) > last_log_id]
                if new_logs:
                    # Reset idle timer upon receiving fresh logs/heartbeats (Keep-Alive)
                    idle_iterations = 0
                new_logs.sort(key=lambda r: r.get("log_id", 0))

                for row in new_logs:
                    log_id = row.get("log_id", 0)
                    if log_id > last_log_id:
                        last_log_id = log_id

                    stage = str(row.get("stage", "PROCESSING"))
                    severity = str(row.get("severity", "INFO"))
                    message = str(row.get("message", ""))
                    raw_ts = row.get("timestamp")

                    if isinstance(raw_ts, datetime):
                        ts_str = raw_ts.isoformat()
                    elif raw_ts:
                        ts_str = str(raw_ts)
                    else:
                        ts_str = datetime.now(timezone.utc).isoformat()

                    # Emit PIPELINE_STAGE_CHANGED if stage is new
                    if stage not in emitted_stages and stage not in ("ERROR", "UNKNOWN"):
                        emitted_stages.add(stage)
                        progress = STAGE_PROGRESS_MAP.get(stage, 50)
                        stage_payload = {
                            "stage": stage,
                            "progress_percentage": progress,
                        }
                        yield f"event: PIPELINE_STAGE_CHANGED\ndata: {json.dumps(stage_payload)}\n\n"

                    # Emit LOG_EMITTED
                    log_payload = {
                        "timestamp": ts_str,
                        "severity": severity,
                        "stage": stage,
                        "message": message,
                    }
                    yield f"event: LOG_EMITTED\ndata: {json.dumps(log_payload)}\n\n"

            # 2. Check run lifecycle status in analysis_runs
            run_rep = await db.get_records_from_analysis_runs(find_only_first=True, run_id=run_id)
            if run_rep.success and run_rep.data:
                run_row = run_rep.data
                status = str(run_row.get("status", "PROCESSING"))

                if status not in ("QUEUED", "PROCESSING", "PARSING"):
                    # Status has reached terminal or degraded state
                    if status in ("COMPLETED", "DEGRADED"):
                        # Emit SUBMODULE_STATUS_UPDATED for all submodules in submodules_reports
                        sub_reports = run_row.get("submodules_reports") or []
                        for sm in sub_reports:
                            raw_code = sm.get("submodule_code") or sm.get("submodule_id") or ""
                            try:
                                long_id = ml_submodule_to_api(raw_code)
                            except KeyError:
                                long_id = str(raw_code)

                            sm_status = str(sm.get("status", "SUCCESS"))
                            sm_verdict = str(sm.get("verdict", "OPTIMAL"))

                            if sm_status == "DATA_ABSENT":
                                sm_status = "BYPASSED"
                                sm_verdict = "DATA_ABSENT"
                            elif sm_status == "ERROR":
                                sm_status = "FAILED"

                            sub_payload = {
                                "submodule_id": long_id,
                                "status": sm_status,
                                "verdict": sm_verdict,
                            }
                            yield f"event: SUBMODULE_STATUS_UPDATED\ndata: {json.dumps(sub_payload)}\n\n"

                        # Terminal event: PIPELINE_COMPLETE
                        raw_score = run_row.get("universal_score")
                        score_val = float(raw_score) if raw_score is not None else 50.0
                        complete_payload = {
                            "run_id": str(run_id),
                            "status": "COMPLETED",
                            "universal_score": round(score_val, 2),
                            "redirect_url": f"/analyze/report/{run_id}",
                        }
                        yield f"event: PIPELINE_COMPLETE\ndata: {json.dumps(complete_payload)}\n\n"
                        break

                    elif status == "FAILED":
                        failure_reason = run_row.get("failure_reason") or "Analysis pipeline execution failed."
                        fail_payload = {
                            "run_id": str(run_id),
                            "error": str(failure_reason),
                        }
                        yield f"event: PIPELINE_FAILED\ndata: {json.dumps(fail_payload)}\n\n"
                        break

            # Poll interval: 200ms
            await asyncio.sleep(0.20)
        else:
            logger.warning(
                "SSE telemetry stream idle-timed out after %d iterations for run %s",
                max_idle_iterations,
                run_id,
            )
            fail_payload = {
                "run_id": str(run_id),
                "error": f"Pipeline execution telemetry stream idle-timed out after {int(timeout_guard_sec)} seconds.",
            }
            yield f"event: PIPELINE_FAILED\ndata: {json.dumps(fail_payload)}\n\n"

    except asyncio.CancelledError:
        logger.info("SSE client disconnected from stream for run %s", run_id)
        raise


__all__ = ["stream_telemetry_from_db", "STAGE_PROGRESS_MAP"]
