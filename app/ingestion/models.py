from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SensorData(Base):
    """
    Core ingestion table.
    Designed for high write frequency and time-series queries.
    """

    __tablename__ = "sensor_data"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)

    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)

    soil_moisture: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# Composite index for fast time-series queries per device
Index(
    "idx_device_created_at",
    SensorData.device_id,
    SensorData.created_at.desc(),
)
