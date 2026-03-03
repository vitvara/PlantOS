from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class SensorIngestRequest(BaseModel):
    """
    Payload received from ESP32 devices.
    """

    device_id: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Unique device identifier",
    )

    temperature: Optional[float] = Field(
        None,
        ge=-50,
        le=150,
        description="Temperature in Celsius",
    )

    humidity: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Humidity percentage",
    )

    soil_moisture: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Soil moisture percentage",
    )

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        if " " in v:
            raise ValueError("device_id must not contain spaces")
        return v


class SensorIngestResponse(BaseModel):
    """
    Response returned after successful ingestion.
    """

    status: str = "accepted"
    device_id: str
    timestamp: datetime