"""
FastAPI Application Entrypoint for GraeaeEye Smart Credit & Cash Flow Risk Engine.

Configures async lifespan for defensive database pooling, global CORS middleware,
static files mount for frontend templates, standardized P10 error handlers,
and registers API v1 routes.
"""
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fintech_app.core.config import settings
import inspect
from .api.router import api_router

logger = logging.getLogger("fintech_app")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Defensive check and initialization of Database connection pool
db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application lifecycle: defensive DB connection and graceful shutdown."""
    global db_pool
    logger.info("Initializing GraeaeEye API startup lifecycle...")

    if not settings.use_mock_engine:
        if hasattr(app.state, "db") and app.state.db is not None:
            db_inst = app.state.db
            if hasattr(db_inst, "open") and not getattr(db_inst, "is_open", False):
                await db_inst.open()
            db_pool = db_inst
            logger.info("Injected database instance opened successfully.")
        else:
            try:
                from fintech_app.db.mock_connection import MockDatabase

                db_inst = MockDatabase.get_instance()
                await db_inst.open()
                db_pool = db_inst
                app.state.db = db_pool
                logger.info("MockDatabase opened successfully for in-process execution.")
            except Exception as exc:
                logger.warning("Database initialization failed: %s. DB remains unavailable.", exc)
                db_pool = None
                app.state.db = None
    else:
        logger.info("Operating in mock engine mode (use_mock_engine=True).")
        if not hasattr(app.state, "db"):
            app.state.db = None

    yield

    logger.info("Executing GraeaeEye API shutdown sequence...")
    if db_pool is not None:
        try:
            if hasattr(db_pool, "close"):
                res = db_pool.close()
                if inspect.isawaitable(res):
                    await res
            elif hasattr(db_pool, "aclose"):
                await db_pool.aclose()
            logger.info("Database pool closed successfully.")
        except Exception as exc:
            logger.error("Error encountered while closing database pool: %s", exc)
        finally:
            db_pool = None


app = FastAPI(
    title="GraeaeEye API",
    description="Smart Credit & Cash Flow Risk Engine for SMEs (Phase 1 Backend API)",
    version="0.1.4",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Configuration
raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
)
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Router
app.include_router(api_router)


@app.get("/health", tags=["Health Check"])
async def health_check():
    """Root health check probe matching upstream."""
    return {"status": "ok", "service": "GraeaeEye API"}


# =====================================================================
# GLOBAL EXCEPTION HANDLERS (Rule P10: Standardized Error Envelope)
# =====================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Standardizes all HTTPExceptions into {"detail": str, "code": str}."""
    if isinstance(exc.detail, dict) and "detail" in exc.detail and "code" in exc.detail:
        payload = exc.detail
    else:
        # Generate canonical code from HTTP status code
        status_code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "UNPROCESSABLE_ENTITY",
            500: "INTERNAL_ERROR",
        }
        code = status_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        payload = {"detail": str(exc.detail), "code": code}

    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Standardizes request validation failures into {"detail": str, "code": "VALIDATION_ERROR"}."""
    error_messages = []
    for err in exc.errors():
        loc = " -> ".join(str(elem) for elem in err.get("loc", []))
        msg = err.get("msg", "invalid")
        error_messages.append(f"{loc}: {msg}")

    detail_str = "; ".join(error_messages) if error_messages else "Request validation failed."
    logger.warning(
        "Request validation failed on %s %s: %s",
        request.method,
        request.url.path,
        detail_str,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail_str, "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches all unhandled exceptions and returns a sanitized 500 without leaking tracebacks."""
    logger.exception(
        "Unhandled server exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred.",
            "code": "INTERNAL_ERROR",
        },
    )


# =====================================================================
# STATIC ASSETS & SPA SERVING (Upstream origin/dev)
# =====================================================================

STATIC_DIR = Path(__file__).resolve().parent / "static"

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_spa():
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(
            {"detail": "SPA index.html not found.", "code": "NOT_FOUND"},
            status_code=404,
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_fav():
        fav_file = STATIC_DIR / "favicon.ico"
        if fav_file.is_file():
            return FileResponse(fav_file)
        return JSONResponse(
            {"detail": "Favicon not found.", "code": "NOT_FOUND"},
            status_code=404,
        )
else:
    logger.warning("STATIC_DIR '%s' does not exist; SPA serving disabled.", STATIC_DIR)
