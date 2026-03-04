"""
Versioned REST endpoint for sensor data ingestion.

Mounted under ``/api/v1`` by the v1 router.
Devices must supply an ``X-API-Key`` header matching the configured secret.

HTTP error mapping:

* 202 Accepted      — reading persisted
* 400 Bad Request   — no measurement values provided
* 401 Unauthorized  — invalid API key
* 422 Unprocessable — schema validation failure
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_api_key, get_ingestion_service
from app.ingestion.exceptions import DeviceNotAuthorized, InvalidSensorPayload
from app.ingestion.schemas import SensorIngestRequest, SensorIngestResponse
from app.ingestion.service import IngestionService


router = APIRouter(tags=["ingestion"])


@router.post(
    "/ingest",
    response_model=SensorIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_sensor_data(
    payload: SensorIngestRequest,
    api_key: str = Depends(get_api_key),
    service: IngestionService = Depends(get_ingestion_service),
) -> SensorIngestResponse:
    """
    Receive sensor data from ESP32 devices.

    Header required:
        X-API-Key: <your-secret>
    """
    try:
        return service.ingest(payload, api_key)
    except DeviceNotAuthorized as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except InvalidSensorPayload as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
