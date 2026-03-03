from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.health.models import PlantHealthLog


class HealthLogRepository:
    """
    Persistence layer for plant health analysis logs.
    Ordered newest-first throughout.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        plant_id: int,
        image_paths: List[str],
        health_score: int,
        summary: str,
        issues: List[str],
        suggestions: List[str],
    ) -> PlantHealthLog:
        log = PlantHealthLog(
            plant_id=plant_id,
            image_paths=image_paths,
            health_score=health_score,
            summary=summary,
            issues=issues,
            suggestions=suggestions,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def get_by_plant(self, plant_id: int) -> List[PlantHealthLog]:
        stmt = (
            select(PlantHealthLog)
            .where(PlantHealthLog.plant_id == plant_id)
            .order_by(PlantHealthLog.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_latest_by_plant(self, plant_id: int) -> Optional[PlantHealthLog]:
        stmt = (
            select(PlantHealthLog)
            .where(PlantHealthLog.plant_id == plant_id)
            .order_by(PlantHealthLog.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()
