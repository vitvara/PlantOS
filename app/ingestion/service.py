"""
Business-logic layer for the sensor ingestion domain.

Responsibilities
----------------
* Authenticating inbound sensor payloads via API key.
* Validating that at least one measurement value is present.
* Persisting raw sensor readings via :class:`~app.ingestion.repository.SensorDataRepository`.

Not responsible for
-------------------
* HTTP concerns — see ``app/api/v1/ingest.py``.
* Direct database queries — delegated to :class:`~app.ingestion.repository.SensorDataRepository`.

Typical usage
-------------
::

    # Via dependency injection (production)
    from app.core.factory import ServiceFactory
    svc = ServiceFactory.ingestion_service(db)
    result = svc.ingest(payload, api_key="secret")
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, log_call
from app.ingestion.exceptions import DeviceNotAuthorized, InvalidSensorPayload
from app.ingestion.repository import SensorDataRepository
from app.ingestion.schemas import SensorIngestRequest, SensorIngestResponse


logger   = get_logger(__name__)
settings = get_settings()


class IngestionService:
    """
    Orchestrates sensor data ingestion.

    Responsibilities:
        - API key authentication
        - Domain-level payload validation
        - Sensor record persistence

    Not responsible for:
        - HTTP concerns (use routes layer)
        - Direct DB queries (use SensorDataRepository)

    Args:
        db: SQLAlchemy Session injected by FastAPI dependency.
    """

    def __init__(self, db: Session) -> None:
        self.repository = SensorDataRepository(db)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    def ingest(
        self,
        payload: SensorIngestRequest,
        api_key: str,
    ) -> SensorIngestResponse:
        """
        Authenticate, validate, and persist a sensor reading.

        Args:
            payload: Validated sensor data from the ESP32 device.
            api_key: Value from the ``X-API-Key`` request header.

        Returns:
            :class:`~app.ingestion.schemas.SensorIngestResponse` with
            ``device_id`` and acceptance ``timestamp``.

        Raises:
            DeviceNotAuthorized: If *api_key* does not match the configured secret.
            InvalidSensorPayload: If all measurement fields are ``None``.
        """
        self._authorize(api_key)
        self._business_validate(payload)

        record = self.repository.create(payload)

        return SensorIngestResponse(
            device_id=record.device_id,
            timestamp=record.created_at,
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _authorize(self, api_key: str) -> None:
        """
        Verify the API key against the configured secret.

        Args:
            api_key: Key provided by the caller.

        Raises:
            DeviceNotAuthorized: If the key does not match.
        """
        if api_key != settings.iot_api_key:
            raise DeviceNotAuthorized("Invalid API key")

    def _business_validate(self, payload: SensorIngestRequest) -> None:
        """
        Domain-level validation beyond schema constraints.

        Ensures at least one sensor measurement is present.

        Args:
            payload: The inbound sensor request.

        Raises:
            InvalidSensorPayload: If all measurement fields are ``None``.
        """
        if (
            payload.temperature  is None
            and payload.humidity     is None
            and payload.soil_moisture is None
        ):
            raise InvalidSensorPayload("At least one sensor value must be provided")
