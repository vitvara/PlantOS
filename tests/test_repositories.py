"""Unit tests for repository layer."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.health.repository import HealthLogRepository
from app.ingestion.repository import SensorDataRepository
from app.ingestion.schemas import SensorIngestRequest
from app.plant.repository import PlantRepository
from app.ui.repository import SensorQueryRepository


# ---------------------------------------------------------------------------
# PlantRepository
# ---------------------------------------------------------------------------

class TestPlantRepository:
    def test_create_and_fetch_by_id(self, db):
        repo = PlantRepository(db)
        plant = repo.create(name="Rose", device_id="PR001")
        db.flush()
        fetched = repo.get_by_id(plant.id)
        assert fetched is not None
        assert fetched.name == "Rose"

    def test_get_by_device_id(self, db):
        repo = PlantRepository(db)
        repo.create(name="Fern", device_id="PR002")
        db.flush()
        fetched = repo.get_by_device_id("PR002")
        assert fetched is not None
        assert fetched.name == "Fern"

    def test_get_by_id_missing_returns_none(self, db):
        repo = PlantRepository(db)
        assert repo.get_by_id(99999) is None

    def test_get_by_device_id_missing_returns_none(self, db):
        repo = PlantRepository(db)
        assert repo.get_by_device_id("NOTEXIST") is None

    def test_list_all_ordered_newest_first(self, db):
        repo = PlantRepository(db)
        repo.create(name="A", device_id="PR003")
        db.flush()
        repo.create(name="B", device_id="PR004")
        db.flush()
        plants = repo.list_all()
        assert len(plants) == 2
        assert plants[0].name == "B"

    def test_update_image(self, db):
        repo = PlantRepository(db)
        plant = repo.create(name="Cactus", device_id="PR005")
        db.flush()
        updated = repo.update_image(plant, "new_image.jpg")
        assert updated.image_path == "new_image.jpg"

    def test_update_species(self, db):
        repo = PlantRepository(db)
        plant = repo.create(name="Orchid", device_id="PR006")
        db.flush()
        updated = repo.update_species(
            plant,
            species="Orchidaceae",
            care_guide={"Watering": "weekly"},
            identified_at=datetime.now(timezone.utc),
            species_thai="กล้วยไม้",
            confidence="High",
        )
        assert updated.species == "Orchidaceae"
        assert updated.species_thai == "กล้วยไม้"
        assert updated.confidence == "High"

    def test_delete_plant(self, db):
        repo = PlantRepository(db)
        plant = repo.create(name="Tulip", device_id="PR007")
        db.flush()
        repo.delete(plant)
        db.flush()
        assert repo.get_by_id(plant.id) is None


# ---------------------------------------------------------------------------
# HealthLogRepository
# ---------------------------------------------------------------------------

class TestHealthLogRepository:
    def _make_plant(self, db):
        from app.plant.repository import PlantRepository
        repo = PlantRepository(db)
        plant = repo.create(name="Test", device_id=f"HR{id(db)}"[:10])
        db.flush()
        return plant

    def test_create_log(self, db):
        plant = PlantRepository(db).create(name="T1", device_id="HL001")
        db.flush()
        repo = HealthLogRepository(db)
        log = repo.create(
            plant_id=plant.id,
            image_paths=["health/a.jpg"],
            health_score=80,
            summary="Good",
            issues=["yellowing"],
            suggestions=["water more"],
        )
        db.flush()
        assert log.id is not None
        assert log.health_score == 80

    def test_get_by_plant_empty(self, db):
        plant = PlantRepository(db).create(name="T2", device_id="HL002")
        db.flush()
        repo = HealthLogRepository(db)
        assert repo.get_by_plant(plant.id) == []

    def test_get_latest_none(self, db):
        plant = PlantRepository(db).create(name="T3", device_id="HL003")
        db.flush()
        repo = HealthLogRepository(db)
        assert repo.get_latest_by_plant(plant.id) is None

    def test_delete_all_by_plant(self, db):
        plant = PlantRepository(db).create(name="T4", device_id="HL004")
        db.flush()
        repo = HealthLogRepository(db)
        for score in (60, 70):
            repo.create(
                plant_id=plant.id,
                image_paths=[],
                health_score=score,
                summary="ok",
                issues=[],
                suggestions=[],
            )
        db.flush()
        repo.delete_all_by_plant(plant.id)
        assert repo.get_by_plant(plant.id) == []

    def test_latest_returns_most_recent(self, db):
        plant = PlantRepository(db).create(name="T5", device_id="HL005")
        db.flush()
        repo = HealthLogRepository(db)
        repo.create(plant_id=plant.id, image_paths=[], health_score=60,
                    summary="ok", issues=[], suggestions=[])
        db.flush()
        repo.create(plant_id=plant.id, image_paths=[], health_score=90,
                    summary="great", issues=[], suggestions=[])
        db.flush()
        latest = repo.get_latest_by_plant(plant.id)
        assert latest.health_score == 90


# ---------------------------------------------------------------------------
# SensorDataRepository
# ---------------------------------------------------------------------------

class TestSensorDataRepository:
    def test_create_sensor_record(self, db):
        repo = SensorDataRepository(db)
        payload = SensorIngestRequest(device_id="SD001", temperature=22.5, humidity=60.0)
        record = repo.create(payload)
        db.flush()
        assert record.id is not None
        assert record.device_id == "SD001"

    def test_get_latest_by_device_empty(self, db):
        repo = SensorDataRepository(db)
        result = repo.get_latest_by_device("NOTHERE")
        assert result is None

    def test_get_latest_by_device_returns_record(self, db):
        repo = SensorDataRepository(db)
        payload = SensorIngestRequest(device_id="SD002", temperature=22.5)
        repo.create(payload)
        db.flush()
        result = repo.get_latest_by_device("SD002")
        assert result is not None
        assert result.temperature == 22.5


# ---------------------------------------------------------------------------
# SensorQueryRepository
# ---------------------------------------------------------------------------

class TestSensorQueryRepository:
    def test_get_timeseries_empty(self, db):
        repo = SensorQueryRepository(db)
        result = repo.get_timeseries("NOTHERE", limit=10)
        assert result == []

    def test_get_timeseries_returns_records(self, db):
        ingest_repo = SensorDataRepository(db)
        for i in range(3):
            ingest_repo.create(SensorIngestRequest(device_id="SQ001", temperature=float(i)))
        db.flush()
        query_repo = SensorQueryRepository(db)
        result = query_repo.get_timeseries("SQ001", limit=10)
        assert len(result) == 3

    def test_get_distinct_devices(self, db):
        repo = SensorDataRepository(db)
        for dev in ("SQ002", "SQ003", "SQ002"):
            repo.create(SensorIngestRequest(device_id=dev, temperature=20.0))
        db.flush()
        query_repo = SensorQueryRepository(db)
        devices = query_repo.get_distinct_devices()
        assert "SQ002" in devices
        assert "SQ003" in devices

    def test_get_timeseries_since_returns_within_window(self, db):
        from datetime import timedelta
        ingest_repo = SensorDataRepository(db)
        for i in range(5):
            ingest_repo.create(SensorIngestRequest(device_id="SQ010", temperature=float(i)))
        db.flush()
        query_repo = SensorQueryRepository(db)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        result = query_repo.get_timeseries_since("SQ010", since=since)
        assert len(result) == 5

    def test_get_timeseries_since_excludes_old_records(self, db):
        from datetime import timedelta
        from app.ingestion.models import SensorData
        ingest_repo = SensorDataRepository(db)
        # Insert a record with a future "since" so it falls outside the window
        ingest_repo.create(SensorIngestRequest(device_id="SQ011", temperature=1.0))
        db.flush()
        query_repo = SensorQueryRepository(db)
        # Use a future "since" so the record is excluded
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        result = query_repo.get_timeseries_since("SQ011", since=future)
        assert result == []

    def test_get_timeseries_since_asc_order(self, db):
        from datetime import timedelta
        ingest_repo = SensorDataRepository(db)
        for i in range(3):
            ingest_repo.create(SensorIngestRequest(device_id="SQ012", temperature=float(i)))
        db.flush()
        query_repo = SensorQueryRepository(db)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        result = query_repo.get_timeseries_since("SQ012", since=since)
        timestamps = [r.created_at for r in result]
        assert timestamps == sorted(timestamps)

    def test_get_timeseries_since_empty_device(self, db):
        from datetime import timedelta
        query_repo = SensorQueryRepository(db)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        result = query_repo.get_timeseries_since("NOTEXIST", since=since)
        assert result == []
