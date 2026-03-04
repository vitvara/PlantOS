"""
Top-level router — wires versioned API and UI sub-routers into the application.

REST API routes live under ``/api/v1/`` (see :mod:`app.api.v1.router`).
UI / template routes are unversioned (see :mod:`app.ui.routes`).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.router import router as v1_router
from app.ui.routes import router as ui_router

api_router = APIRouter()

api_router.include_router(v1_router)
api_router.include_router(ui_router)
