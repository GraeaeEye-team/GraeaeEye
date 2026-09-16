"""
Точка входа веб-приложения FastAPI.
Инициализирует экземпляр приложения, подключает роутеры API v1 и глобальные middleware.
"""
from fastapi import FastAPI
from src.fintech_app.api.router import api_router

app = FastAPI(
    title="GraeaeEye API",
    description="Smart Credit & Cash Flow Risk Engine for SMEs",
    version="0.1.0",
)

app.include_router(api_router)


@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok", "service": "GraeaeEye API"}
