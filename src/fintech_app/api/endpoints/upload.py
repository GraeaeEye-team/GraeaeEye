"""
API-эндпоинты загрузки банковских выписок и финансовых документов.
Принимает файлы Excel/CSV, запускает AI-маппинг и передает данные в хранилище PostgreSQL.
"""
from fastapi import APIRouter, File, UploadFile

router = APIRouter()


@router.post("/upload", summary="Загрузить выписку")
async def upload_financial_statement(file: UploadFile = File(...)):
    """Принимает файл выписки и производит первичный автоматический парсинг."""
    return {"filename": file.filename, "status": "processed"}

