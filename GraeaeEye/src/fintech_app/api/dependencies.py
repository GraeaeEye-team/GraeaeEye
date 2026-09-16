"""
Зависимости (Dependencies) для эндпоинтов FastAPI.
Управляет внедрением сессий подключения к PostgreSQL и глобальными ресурсами.
"""
from typing import Generator
from src.fintech_app.core.config import settings


def get_db_connection() -> Generator[None, None, None]:
    """Предоставляет соединение с базой данных в контексте HTTP-запроса."""
    yield None

