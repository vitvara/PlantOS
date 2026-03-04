"""
Aggregates all v1 API sub-routers under the ``/api/v1`` prefix.

To add a new v1 resource:
1. Create ``app/api/v1/<resource>.py`` with its own ``APIRouter``.
2. Import and include it here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health, ingest, plants


router = APIRouter(prefix="/api/v1")

router.include_router(plants.router)
router.include_router(ingest.router)
router.include_router(health.router)
