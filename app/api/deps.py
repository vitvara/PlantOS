from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.health.service import PlantHealthService
from app.ingestion.service import IngestionService
from app.plant.service import PlantService
from app.ui.service import DashboardService


# -------------------------
# API Key
# -------------------------
def get_api_key(x_api_key: str = Header(...)) -> str:
    """
    Extract API key from X-API-Key header.
    ESP32 must send: X-API-Key: your-secret-key
    """
    return x_api_key


# -------------------------
# Service Factories
# -------------------------
def get_ingestion_service(db: Session = Depends(get_db)) -> IngestionService:
    return IngestionService(db)


def get_plant_service(db: Session = Depends(get_db)) -> PlantService:
    return PlantService(db)


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    return DashboardService(db)


def get_health_service(db: Session = Depends(get_db)) -> PlantHealthService:
    return PlantHealthService(db)
