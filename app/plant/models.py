from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Plant(Base):
    """
    Plant domain model.
    One plant = one device.
    """

    __tablename__ = "plants"
    __table_args__ = (UniqueConstraint("device_id", name="uq_plants_device_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Species identification (set by OpenAI from profile image)
    species: Mapped[str | None] = mapped_column(Text, nullable=True)
    species_thai: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    care_guide: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    species_identified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
