from fastapi import APIRouter

from app.health.routes import router as health_router
from app.ingestion.routes import router as ingestion_router
from app.plant.routes import router as plant_router
from app.ui.routes import router as ui_router

api_router = APIRouter()

api_router.include_router(ingestion_router)
api_router.include_router(plant_router)
api_router.include_router(health_router)
api_router.include_router(ui_router)