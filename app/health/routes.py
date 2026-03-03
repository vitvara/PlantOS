from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_health_service, get_plant_service
from app.health.exceptions import AnalysisError, TooManyImages
from app.health.schemas import HealthLogResponse
from app.health.service import PlantHealthService
from app.plant.exceptions import PlantNotFound
from app.plant.service import PlantService


router = APIRouter(prefix="/plants", tags=["Health"])


@router.post("/{plant_id}/health", response_model=HealthLogResponse, status_code=status.HTTP_201_CREATED)
async def analyze_plant_health(
    plant_id: int,
    files: List[UploadFile] = File(...),
    health_service: PlantHealthService = Depends(get_health_service),
    plant_service: PlantService = Depends(get_plant_service),
) -> HealthLogResponse:
    try:
        plant = plant_service.get_plant(plant_id)
    except PlantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    try:
        images = [await f.read() for f in files]
        filenames = [f.filename for f in files]
        return await health_service.analyze(
            plant_id=plant_id,
            images=images,
            filenames=filenames,
            species=plant.species,
        )
    except TooManyImages as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except AnalysisError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get("/{plant_id}/health", response_model=List[HealthLogResponse])
def get_health_history(
    plant_id: int,
    health_service: PlantHealthService = Depends(get_health_service),
    plant_service: PlantService = Depends(get_plant_service),
) -> List[HealthLogResponse]:
    try:
        plant_service.get_plant(plant_id)
    except PlantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return health_service.get_history(plant_id)
