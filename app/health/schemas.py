from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class HealthLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    image_paths: List[str]
    health_score: int
    summary: str
    issues: List[str]
    suggestions: List[str]
    created_at: datetime
