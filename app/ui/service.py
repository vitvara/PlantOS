from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ui.repository import SensorQueryRepository
from app.ui.schemas import DashboardData, TimeSeriesPoint

SensorStatus = Literal["active", "failed", "no_data"]


class DashboardService:
    """
    Service layer for dashboard UI flow.
    Responsible for:
    - Orchestrating read queries
    - Transforming ORM → schema
    - Applying business-level read constraints
    """

    DEFAULT_LIMIT = 200
    MAX_LIMIT = 1000

    def __init__(self, db: Session):
        self.repository = SensorQueryRepository(db)

    # -------------------------
    # Public API
    # -------------------------
    def get_dashboard_data(
        self,
        device_id: str,
        limit: Optional[int] = None,
    ) -> DashboardData:
        """
        Fetch timeseries data for dashboard rendering.
        """

        limit = self._normalize_limit(limit)

        rows = self.repository.get_timeseries(
            device_id=device_id,
            limit=limit,
        )

        points = [
            TimeSeriesPoint(
                timestamp=row.created_at,
                temperature=row.temperature,
                humidity=row.humidity,
                soil_moisture=row.soil_moisture,
            )
            for row in rows
        ]

        return DashboardData(
            device_id=device_id,
            points=points,
        )

    def get_sensor_history_for_hours(
        self,
        device_id: str,
        hours: float,
    ) -> DashboardData:
        """
        Fetch time-windowed sensor data ordered oldest→newest.
        Used for time-proportional chart rendering.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = self.repository.get_timeseries_since(device_id=device_id, since=since)
        points = [
            TimeSeriesPoint(
                timestamp=row.created_at,
                temperature=row.temperature,
                humidity=row.humidity,
                soil_moisture=row.soil_moisture,
            )
            for row in rows
        ]
        return DashboardData(device_id=device_id, points=points)

    def get_available_devices(self):
        return self.repository.get_distinct_devices()

    def get_sensor_status(self, device_id: str) -> "SensorStatus":
        """
        Return the connectivity status of a sensor device.

        - "no_data"  — no readings ever recorded
        - "active"   — last reading within sensor_timeout_seconds
        - "failed"   — last reading older than sensor_timeout_seconds
        """
        latest = self.repository.get_latest_by_device(device_id)
        if latest is None:
            return "no_data"

        timeout = get_settings().sensor_timeout_seconds
        # SQLite returns naive datetimes; normalise to UTC-aware before subtracting.
        ts = latest.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return "active" if age <= timeout else "failed"

    # -------------------------
    # Private helpers
    # -------------------------
    def _normalize_limit(self, limit: Optional[int]) -> int:
        """
        Enforce safe upper bounds to protect DB.
        """
        if limit is None:
            return self.DEFAULT_LIMIT

        if limit <= 0:
            return self.DEFAULT_LIMIT

        if limit > self.MAX_LIMIT:
            return self.MAX_LIMIT

        return limit