"""
FastAPI dependency functions — single source of truth for service construction.

All service instances are obtained via :class:`~app.core.factory.ServiceFactory`
so that dependency injection and test overrides are handled in one place.
"""

from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.factory import ServiceFactory
from app.health.service import PlantHealthService
from app.ingestion.service import IngestionService
from app.plant.service import PlantService
from app.ui.service import DashboardService


# ------------------------------------------------------------------ #
# API Key                                                              #
# ------------------------------------------------------------------ #

def get_api_key(x_api_key: str = Header(...)) -> str:
    """
    Extract the API key from the ``X-API-Key`` request header.

    ESP32 devices must send: ``X-API-Key: <secret>``
    """
    return x_api_key


# ------------------------------------------------------------------ #
# Service dependencies                                                 #
# ------------------------------------------------------------------ #

def get_plant_service(db: Session = Depends(get_db)) -> PlantService:
    return ServiceFactory.plant_service(db)


def get_health_service(db: Session = Depends(get_db)) -> PlantHealthService:
    return ServiceFactory.health_service(db)


def get_ingestion_service(db: Session = Depends(get_db)) -> IngestionService:
    return ServiceFactory.ingestion_service(db)


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    return ServiceFactory.dashboard_service(db)
