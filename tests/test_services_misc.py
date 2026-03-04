"""Tests for IngestionService and DashboardService."""
from __future__ import annotations

import pytest

from app.ingestion.exceptions import DeviceNotAuthorized, InvalidSensorPayload
from app.ingestion.schemas import SensorIngestRequest
from app.ingestion.service import IngestionService
from app.ui.service import DashboardService


# ---------------------------------------------------------------------------
# IngestionService
# ---------------------------------------------------------------------------

class TestIngestionService:
    def test_valid_ingest(self, db):
        svc = IngestionService(db)
        payload = SensorIngestRequest(device_id="IS001", temperature=22.0)
        result = svc.ingest(payload, api_key="supersecretkey")
        assert result.device_id == "IS001"
        assert result.status == "accepted"

    def test_wrong_api_key_raises(self, db):
        svc = IngestionService(db)
        payload = SensorIngestRequest(device_id="IS002", temperature=22.0)
        with pytest.raises(DeviceNotAuthorized):
            svc.ingest(payload, api_key="wrongkey")

    def test_all_none_raises_invalid_payload(self, db):
        svc = IngestionService(db)
        payload = SensorIngestRequest(device_id="IS003")
        with pytest.raises(InvalidSensorPayload):
            svc.ingest(payload, api_key="supersecretkey")

    def test_ingest_all_sensors(self, db):
        svc = IngestionService(db)
        payload = SensorIngestRequest(
            device_id="IS004", temperature=25.0, humidity=60.0, soil_moisture=40.0
        )
        result = svc.ingest(payload, api_key="supersecretkey")
        assert result.device_id == "IS004"


# ---------------------------------------------------------------------------
# DashboardService
# ---------------------------------------------------------------------------

class TestDashboardService:
    def test_empty_dashboard_data(self, db):
        svc = DashboardService(db)
        data = svc.get_dashboard_data(device_id="NODEV")
        assert data.device_id == "NODEV"
        assert data.points == []

    def test_dashboard_with_data(self, db):
        from app.ingestion.repository import SensorDataRepository
        from app.ingestion.schemas import SensorIngestRequest
        ingest = SensorDataRepository(db)
        for i in range(5):
            ingest.create(SensorIngestRequest(device_id="DS001", temperature=float(20 + i)))
        db.flush()
        svc = DashboardService(db)
        data = svc.get_dashboard_data(device_id="DS001", limit=10)
        assert len(data.points) == 5

    def test_normalize_limit_none_uses_default(self, db):
        svc = DashboardService(db)
        assert svc._normalize_limit(None) == DashboardService.DEFAULT_LIMIT

    def test_normalize_limit_zero_uses_default(self, db):
        svc = DashboardService(db)
        assert svc._normalize_limit(0) == DashboardService.DEFAULT_LIMIT

    def test_normalize_limit_above_max_clamps(self, db):
        svc = DashboardService(db)
        assert svc._normalize_limit(9999) == DashboardService.MAX_LIMIT

    def test_normalize_limit_valid(self, db):
        svc = DashboardService(db)
        assert svc._normalize_limit(50) == 50

    def test_get_available_devices(self, db):
        from app.ingestion.repository import SensorDataRepository
        from app.ingestion.schemas import SensorIngestRequest
        ingest = SensorDataRepository(db)
        ingest.create(SensorIngestRequest(device_id="DS002", temperature=20.0))
        db.flush()
        svc = DashboardService(db)
        devices = svc.get_available_devices()
        assert "DS002" in devices
