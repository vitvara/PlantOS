from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_dashboard_service, get_health_service, get_plant_service
from app.core.database import get_db
from app.health.exceptions import AnalysisError, TooManyImages
from app.health.service import PlantHealthService
from app.plant.exceptions import (
    DeviceAlreadyRegistered,
    NoProfileImage,
    PlantNotFound,
    SpeciesIdentificationError,
    UnsupportedImageFormat,
)
from app.plant.service import PlantService
from app.ui.service import DashboardService


router = APIRouter(tags=["UI"])

templates = Jinja2Templates(directory="app/templates")


# ------------------------------------------------
# Home → redirect to catalog
# ------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse(url="/catalog", status_code=status.HTTP_302_FOUND)


# ------------------------------------------------
# Plant Catalog
# ------------------------------------------------
@router.get("/catalog", response_class=HTMLResponse)
def catalog(
    request: Request,
    error: Optional[str] = Query(None),
    success: Optional[str] = Query(None),
    plant_service: PlantService = Depends(get_plant_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    health_service: PlantHealthService = Depends(get_health_service),
) -> HTMLResponse:
    plants = plant_service.list_plants()

    registered_ids = {p.device_id for p in plants}
    all_seen_ids = set(dashboard_service.get_available_devices())
    unregistered_devices = sorted(all_seen_ids - registered_ids)

    plant_stats: dict = {}
    for plant in plants:
        latest_health = health_service.get_latest(plant.id)
        plant_stats[plant.id] = {
            "health_score": latest_health.health_score if latest_health else None,
            "sensor_status": dashboard_service.get_sensor_status(plant.device_id),
        }

    return templates.TemplateResponse("catalog.html", {
        "request": request,
        "plants": plants,
        "unregistered_devices": unregistered_devices,
        "plant_stats": plant_stats,
        "error": error,
        "success": success,
    })


@router.post("/catalog/register")
def register_plant(
    name: str = Form(...),
    device_id: str = Form(...),
    plant_service: PlantService = Depends(get_plant_service),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        plant = plant_service.create_plant(name=name, device_id=device_id)
        # Commit BEFORE the 303 redirect — FastAPI yield-dependency cleanup
        # runs after the response is sent, so the follow-up GET could arrive
        # before the transaction is committed and see a 404.
        db.commit()
        return RedirectResponse(
            url=f"/catalog/{plant.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except DeviceAlreadyRegistered as e:
        return RedirectResponse(
            url=f"/catalog?{urlencode({'error': str(e)})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# ------------------------------------------------
# Plant Detail
# ------------------------------------------------
@router.get("/catalog/{plant_id}", response_class=HTMLResponse)
def plant_detail(
    request: Request,
    plant_id: int,
    error: Optional[str] = Query(None),
    success: Optional[str] = Query(None),
    plant_service: PlantService = Depends(get_plant_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    health_service: PlantHealthService = Depends(get_health_service),
) -> HTMLResponse:
    try:
        plant = plant_service.get_plant(plant_id)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail="Plant not found")

    dashboard_data = dashboard_service.get_dashboard_data(device_id=plant.device_id, limit=200)
    latest_sensor = dashboard_data.points[-1] if dashboard_data.points else None
    sensor_status = dashboard_service.get_sensor_status(plant.device_id)

    latest_health = health_service.get_latest(plant_id)

    return templates.TemplateResponse("plant_detail.html", {
        "request": request,
        "plant": plant,
        "latest": latest_sensor,
        "dashboard_data": dashboard_data,
        "sensor_status": sensor_status,
        "latest_health": latest_health,
        "error": error,
        "success": success,
    })


@router.get("/catalog/{plant_id}/sensor-data")
def sensor_data(
    plant_id: int,
    hours: float = Query(24.0, ge=0.5, le=168.0),
    plant_service: PlantService = Depends(get_plant_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> JSONResponse:
    try:
        plant = plant_service.get_plant(plant_id)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail="Plant not found")

    data = dashboard_service.get_sensor_history_for_hours(
        device_id=plant.device_id,
        hours=hours,
    )
    return JSONResponse({
        "device_id": data.device_id,
        "hours": hours,
        "count": len(data.points),
        "points": [
            {
                "t": p.timestamp.isoformat(),
                "temp": p.temperature,
                "hum": p.humidity,
                "soil": p.soil_moisture,
            }
            for p in data.points
        ],
    })


@router.post("/catalog/{plant_id}/delete")
def delete_plant(
    plant_id: int,
    plant_service: PlantService = Depends(get_plant_service),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        plant_service.delete_plant(plant_id)
        db.commit()
        return RedirectResponse(
            url=f"/catalog?{urlencode({'success': 'Plant deleted successfully'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except PlantNotFound:
        raise HTTPException(status_code=404, detail="Plant not found")


@router.post("/catalog/{plant_id}/image")
async def upload_plant_image(
    plant_id: int,
    file: UploadFile = File(...),
    plant_service: PlantService = Depends(get_plant_service),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        content = await file.read()
        plant_service.save_image(
            plant_id=plant_id,
            file_bytes=content,
            filename=file.filename,
        )
        db.commit()
        return RedirectResponse(
            url=f"/catalog/{plant_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except PlantNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnsupportedImageFormat as e:
        return RedirectResponse(
            url=f"/catalog/{plant_id}?{urlencode({'error': str(e)})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/catalog/{plant_id}/identify-species")
async def identify_species(
    plant_id: int,
    plant_service: PlantService = Depends(get_plant_service),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        await plant_service.identify_species(plant_id)
        db.commit()
        return RedirectResponse(
            url=f"/catalog/{plant_id}?{urlencode({'success': 'Species identified successfully'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except PlantNotFound:
        raise HTTPException(status_code=404, detail="Plant not found")
    except NoProfileImage as e:
        return RedirectResponse(
            url=f"/catalog/{plant_id}?{urlencode({'error': str(e)})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except SpeciesIdentificationError as e:
        return RedirectResponse(
            url=f"/catalog/{plant_id}?{urlencode({'error': str(e)})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# ------------------------------------------------
# Health Timeline
# ------------------------------------------------
@router.get("/catalog/{plant_id}/health", response_class=HTMLResponse)
def health_timeline(
    request: Request,
    plant_id: int,
    error: Optional[str] = Query(None),
    plant_service: PlantService = Depends(get_plant_service),
    health_service: PlantHealthService = Depends(get_health_service),
) -> HTMLResponse:
    try:
        plant = plant_service.get_plant(plant_id)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail="Plant not found")

    logs = health_service.get_history(plant_id)

    return templates.TemplateResponse("health_timeline.html", {
        "request": request,
        "plant": plant,
        "logs": logs,
        "error": error,
    })


@router.post("/catalog/{plant_id}/health/analyze")
async def submit_health_analysis(
    plant_id: int,
    files: List[UploadFile] = File(...),
    plant_service: PlantService = Depends(get_plant_service),
    health_service: PlantHealthService = Depends(get_health_service),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        plant = plant_service.get_plant(plant_id)
    except PlantNotFound:
        raise HTTPException(status_code=404, detail="Plant not found")

    images: List[bytes] = []
    filenames: List[str | None] = []
    for f in files:
        if f.filename:
            images.append(await f.read())
            filenames.append(f.filename)

    if not images:
        return RedirectResponse(
            url=f"/catalog/{plant_id}/health?{urlencode({'error': 'Select at least one image'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await health_service.analyze(
            plant_id=plant_id,
            images=images,
            filenames=filenames,
            species=plant.species,
        )
        db.commit()
        return RedirectResponse(
            url=f"/catalog/{plant_id}/health",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except (TooManyImages, AnalysisError) as e:
        return RedirectResponse(
            url=f"/catalog/{plant_id}/health?{urlencode({'error': str(e)})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
