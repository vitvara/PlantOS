"""
Versioned REST endpoints for the plant domain.

All routes are mounted under ``/api/v1/plants`` by the v1 router.
HTTP error mapping:

* 201 Created       — plant registered
* 200 OK            — read / update
* 400 Bad Request   — unsupported image format
* 404 Not Found     — plant does not exist
* 409 Conflict      — device already registered
* 422 Unprocessable — missing profile image for species ID
* 502 Bad Gateway   — AI provider failure
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_plant_service
from app.plant.exceptions import (
    DeviceAlreadyRegistered,
    NoProfileImage,
    PlantNotFound,
    SpeciesIdentificationError,
    UnsupportedImageFormat,
)
from app.plant.schemas import PlantCatalogItem, PlantCreate, PlantResponse
from app.plant.service import PlantService


router = APIRouter(prefix="/plants", tags=["plants"])


@router.post("/", response_model=PlantResponse, status_code=status.HTTP_201_CREATED)
def create_plant(
    payload: PlantCreate,
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Register a new plant with a unique device ID."""
    try:
        return service.create_plant(name=payload.name, device_id=payload.device_id)
    except DeviceAlreadyRegistered as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/", response_model=List[PlantCatalogItem])
def list_plants(
    service: PlantService = Depends(get_plant_service),
) -> List[PlantCatalogItem]:
    """Return all registered plants ordered newest-first."""
    return service.list_plants()


@router.get("/{plant_id}", response_model=PlantResponse)
def get_plant(
    plant_id: int,
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Fetch a single plant by its primary key."""
    try:
        return service.get_plant(plant_id)
    except PlantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{plant_id}/upload-image", response_model=PlantResponse)
async def upload_image(
    plant_id: int,
    file: UploadFile = File(...),
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Upload and persist a profile photo for a plant."""
    try:
        content = await file.read()
        return service.save_image(
            plant_id=plant_id,
            file_bytes=content,
            filename=file.filename,
        )
    except PlantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnsupportedImageFormat as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{plant_id}/identify-species", response_model=PlantResponse)
async def identify_species(
    plant_id: int,
    service: PlantService = Depends(get_plant_service),
) -> PlantResponse:
    """Identify plant species from its profile photo using AI."""
    try:
        return await service.identify_species(plant_id)
    except PlantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except NoProfileImage as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SpeciesIdentificationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
