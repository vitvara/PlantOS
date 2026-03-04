from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from typing import List

from app.ingestion.models import SensorData


class SensorQueryRepository:
    """
    Read-only repository for dashboard queries.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_timeseries(
        self,
        device_id: str,
        limit: int = 200,
    ) -> List[SensorData]:
        """
        Retrieve latest N sensor records for a device.
        Optimized for timeseries dashboard.
        """

        stmt = (
            select(SensorData)
            .where(SensorData.device_id == device_id)
            .order_by(SensorData.created_at.desc())
            .limit(limit)
        )

        result = self.db.execute(stmt)
        rows = result.scalars().all()

        # Reverse for chronological display (oldest → newest)
        return list(reversed(rows))

    def get_timeseries_since(
        self,
        device_id: str,
        since: datetime,
        limit: int = 3000,
    ) -> List[SensorData]:
        """
        Retrieve sensor records for a device from `since` onwards (ASC order).
        Used for time-proportional chart rendering.
        """
        stmt = (
            select(SensorData)
            .where(SensorData.device_id == device_id)
            .where(SensorData.created_at >= since)
            .order_by(SensorData.created_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_latest_by_device(self, device_id: str) -> SensorData | None:
        """Return the single most-recent record for a device, or None."""
        stmt = (
            select(SensorData)
            .where(SensorData.device_id == device_id)
            .order_by(SensorData.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def get_distinct_devices(self) -> List[str]:
        """
        Retrieve available device IDs.
        Used for dropdown selection.
        """

        stmt = select(SensorData.device_id).distinct()
        result = self.db.execute(stmt)
        return [row[0] for row in result.all()]