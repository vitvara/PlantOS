from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import SensorData
from app.ingestion.schemas import SensorIngestRequest


class SensorDataRepository:
    """
    Repository layer for sensor ingestion.
    Responsibilities: persist and query sensor data. No business logic.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: SensorIngestRequest) -> SensorData:
        record = SensorData(
            device_id=payload.device_id,
            temperature=payload.temperature,
            humidity=payload.humidity,
            soil_moisture=payload.soil_moisture,
            # created_at falls back to the model default: datetime.now(timezone.utc)
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_latest_by_device(self, device_id: str) -> SensorData | None:
        stmt = (
            select(SensorData)
            .where(SensorData.device_id == device_id)
            .order_by(SensorData.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()
