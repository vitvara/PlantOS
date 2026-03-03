from sqlalchemy.orm import Session
from typing import Optional

from app.ui.repository import SensorQueryRepository
from app.ui.schemas import DashboardData, TimeSeriesPoint


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

    def get_available_devices(self):
        return self.repository.get_distinct_devices()

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