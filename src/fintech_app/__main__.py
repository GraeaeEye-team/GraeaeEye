"""
Точка входа веб-приложения FastAPI, как модуля python.
См. main.py
"""
from .main import *
import uvicorn

uvicorn.run(app, port=3000, log_level="info")
