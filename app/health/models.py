from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlantHealthLog(Base):
    """
    One record per health analysis session.
    Stores the GPT-4o assessment, score, and paths to the analyzed images.
    """

    __tablename__ = "plant_health_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relative paths under MEDIA_ROOT, e.g. ["health/abc.jpg", "health/def.png"]
    image_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    health_score: Mapped[int] = mapped_column(Integer, nullable=False)

    summary: Mapped[str] = mapped_column(Text, nullable=False)

    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    suggestions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
