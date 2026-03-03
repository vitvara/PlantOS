from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.plant.models import Plant


class PlantRepository:
    """
    Repository layer for Plant domain.
    Responsible only for persistence operations.
    """

    def __init__(self, db: Session):
        self.db = db

    # -------------------------
    # Create
    # -------------------------
    def create(self, name: str, device_id: str) -> Plant:
        plant = Plant(
            name=name,
            device_id=device_id,
        )

        self.db.add(plant)
        self.db.flush()

        return plant

    # -------------------------
    # Read
    # -------------------------
    def get_by_device_id(self, device_id: str) -> Optional[Plant]:
        stmt = select(Plant).where(Plant.device_id == device_id)
        result = self.db.execute(stmt)
        return result.scalars().first()

    def get_by_id(self, plant_id: int) -> Optional[Plant]:
        stmt = select(Plant).where(Plant.id == plant_id)
        result = self.db.execute(stmt)
        return result.scalars().first()

    def list_all(self) -> List[Plant]:
        stmt = select(Plant).order_by(Plant.created_at.desc())
        result = self.db.execute(stmt)
        return result.scalars().all()

    # -------------------------
    # Update
    # -------------------------
    def update_image(self, plant: Plant, image_path: str) -> Plant:
        plant.image_path = image_path
        self.db.flush()
        return plant

    def update_species(
        self,
        plant: Plant,
        species: str,
        care_guide: dict,
        identified_at: datetime,
        species_thai: str | None = None,
        confidence: str | None = None,
    ) -> Plant:
        plant.species = species
        plant.species_thai = species_thai
        plant.confidence = confidence
        plant.care_guide = care_guide
        plant.species_identified_at = identified_at
        self.db.flush()
        return plant

    # -------------------------
    # Delete
    # -------------------------
    def delete(self, plant: Plant) -> None:
        self.db.delete(plant)
        self.db.flush()