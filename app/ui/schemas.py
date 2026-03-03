from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class TimeSeriesPoint(BaseModel):
    """
    Single point for timeseries chart.
    """

    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]
    soil_moisture: Optional[float]


class DashboardData(BaseModel):
    """
    Aggregated structure used by dashboard template.
    """

    device_id: str
    points: List[TimeSeriesPoint]


class DeviceListResponse(BaseModel):
    """
    Device selector abstraction.
    """

    devices: List[str]