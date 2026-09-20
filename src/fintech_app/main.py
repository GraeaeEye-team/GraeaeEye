"""
Точка входа веб-приложения FastAPI.
Инициализирует экземпляр приложения, подключает роутеры API v1 и глобальные middleware.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .api.router import api_router

app = FastAPI(
    title="GraeaeEye API",
    description="Smart Credit & Cash Flow Risk Engine for SMEs",
    version="0.1.4",
)

app.include_router(api_router)

@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok", "service": "GraeaeEye API"}


STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=FileResponse)
async def serve_spa():
    return STATIC_DIR / "index.html"

@app.get("/favicon.ico", response_class=FileResponse)
async def serve_fav():
    return STATIC_DIR / "favicon.ico"

