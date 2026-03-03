from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingestion.repository import SensorDataRepository
from app.ingestion.schemas import SensorIngestRequest, SensorIngestResponse
from app.ingestion.exceptions import DeviceNotAuthorized, InvalidSensorPayload


settings = get_settings()


class IngestionService:
    """
    Business logic layer for sensor ingestion.
    """

    def __init__(self, db: Session):
        self.repository = SensorDataRepository(db)

    # -------------------------
    # Public API
    # -------------------------
    def ingest(
        self,
        payload: SensorIngestRequest,
        api_key: str,
    ) -> SensorIngestResponse:
        """
        Main ingestion entrypoint.
        """

        self._authorize(api_key)
        self._business_validate(payload)

        record = self.repository.create(payload)

        return SensorIngestResponse(
            device_id=record.device_id,
            timestamp=record.created_at,
        )

    # -------------------------
    # Private helpers
    # -------------------------
    def _authorize(self, api_key: str) -> None:
        """
        Basic device authorization.
        Can later be replaced with device registry table.
        """
        if api_key != settings.iot_api_key:
            raise DeviceNotAuthorized("Invalid API key")

    def _business_validate(self, payload: SensorIngestRequest) -> None:
        """
        Domain-level validation beyond schema.
        """

        # Ensure at least one measurement exists
        if (
            payload.temperature is None
            and payload.humidity is None
            and payload.soil_moisture is None
        ):
            raise InvalidSensorPayload(
                "At least one sensor value must be provided"
            )

        # Example future rule:
        # Reject impossible combinations, etc.