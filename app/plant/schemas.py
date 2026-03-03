from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Display name of the plant")
    device_id: str = Field(..., min_length=3, max_length=100, description="Unique device identifier linked to ESP32")


class PlantCreate(PlantBase):
    pass


class PlantAutoRegister(BaseModel):
    device_id: str


class PlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    device_id: str
    image_path: Optional[str]
    species: Optional[str]
    care_guide: Optional[Dict[str, Any]]
    species_identified_at: Optional[datetime]
    created_at: datetime


class PlantCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    device_id: str
    image_path: Optional[str]
    species: Optional[str]
