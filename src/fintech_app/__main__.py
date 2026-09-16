"""
Точка входа веб-приложения FastAPI, как модуля python.
См. main.py
"""
#import .main
import uvicorn

uvicorn.run("main:app", port=3000, log_level="info")
