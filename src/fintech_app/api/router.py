"""
Главный маршрутизатор (Router) API версии 1.
Регистрирует и объединяет эндпоинты модулей загрузки, прогнозирования и сценариев.
"""
from fastapi import APIRouter
from .endpoints import forecast, scenarios, upload

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(upload.router, tags=["Data Ingestion"])
api_router.include_router(forecast.router, tags=["Cash Flow Forecast"])
api_router.include_router(scenarios.router, tags=["What-If Scenarios"])

