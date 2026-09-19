"""
Main API Router for GraeaeEye API v1.

Aggregates authentication and analysis endpoints under the /api/v1 prefix.
"""

from fastapi import APIRouter

from .endpoints import analysis, auth

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(analysis.router, tags=["Analysis", "Health"])
