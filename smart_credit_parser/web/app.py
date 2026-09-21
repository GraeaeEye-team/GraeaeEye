"""
FastAPI Web Application for Smart Credit Data Ingestion Wizard.
Exposes clean REST endpoints for the 4-step wizard and serves responsive UI.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Header, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..app_interface import ParserModuleService

app = FastAPI(
    title="Smart Credit System: Data Parser Wizard",
    description="Universal AI-driven data ingestion module anchored to schema.sql",
    version="1.0.0",
)

# Service instance
ROOT_SCHEMA = Path(__file__).resolve().parent.parent.parent / "schema.sql"
SCHEMA_PATH = Path(
    os.getenv(
        "SCHEMA_PATH",
        str(ROOT_SCHEMA) if ROOT_SCHEMA.exists() else r"c:\Users\skv1d\Downloads\schema.sql"
    )
)
service = ParserModuleService(schema_path=SCHEMA_PATH)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class UpdateMappingRequest(BaseModel):
    target_table: str
    custom_mappings: Dict[str, str]
    save_to_cache: bool = True


class DryRunRequest(BaseModel):
    context_keys: Optional[Dict[str, Any]] = None


class CommitRequest(BaseModel):
    user_id: Optional[str] = "analyst_demo"
    user_role: Optional[str] = "UNDERWRITER"


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Smart Credit Parser Wizard</h1><p>Static files loading...</p>")


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    x_user_id: str = Header(default="analyst_1"),
    x_user_role: str = Header(default="ANALYST"),
):
    """Шаг 1: Загрузка файла и автоматический аудит формата."""
    try:
        content = await file.read()
        summary = service.upload_and_inspect(
            file_bytes=content,
            filename=file.filename or "uploaded_file",
            user_id=x_user_id,
            user_role=x_user_role,
        )
        return summary
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/mapping/{session_id}")
async def get_mapping(session_id: str, target_table: Optional[str] = None):
    """Шаг 2: Получение маппинга колонок."""
    try:
        return service.get_mapping(session_id, target_table_hint=target_table)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/mapping/{session_id}")
async def update_mapping(session_id: str, req: UpdateMappingRequest):
    """Шаг 2: Обновление маппинга человеком."""
    try:
        return service.update_mapping(
            session_id=session_id,
            target_table=req.target_table,
            custom_mappings=req.custom_mappings,
            save_to_cache=req.save_to_cache,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/dry-run/{session_id}")
async def run_dry_run(session_id: str, req: Optional[DryRunRequest] = None):
    """Шаг 3: Запуск предпросмотра (Dry-run)."""
    try:
        ctx = req.context_keys if req else None
        return service.run_dry_run(session_id, context_keys=ctx)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/commit/{session_id}")
async def confirm_and_write(
    session_id: str,
    req: Optional[CommitRequest] = None,
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
):
    """Шаг 4: Атомарная транзакционная запись (Underwriter / Admin)."""
    user_id = (req.user_id if req and req.user_id else None) or x_user_id or "underwriter_1"
    user_role = (req.user_role if req and req.user_role else None) or x_user_role or "UNDERWRITER"

    try:
        return service.confirm_and_write(session_id, user_id=user_id, user_role=user_role)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/history")
async def get_history(limit: int = 50):
    """Получение истории сессий загрузки."""
    return service.get_history(limit=limit)


@app.get("/api/report/{session_id}")
async def download_report(session_id: str, format: str = "markdown"):
    """Скачивание отчета разбора данных."""
    try:
        content = service.download_report(session_id, format_type=format)
        if format.lower() == "markdown":
            return PlainTextResponse(content, media_type="text/markdown")
        return PlainTextResponse(content, media_type="application/json")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
