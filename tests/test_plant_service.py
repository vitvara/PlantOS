"""Unit tests for PlantService."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.health.repository import HealthLogRepository
from app.plant.exceptions import (
    DeviceAlreadyRegistered,
    NoProfileImage,
    PlantNotFound,
    SpeciesIdentificationError,
    UnsupportedImageFormat,
)
from app.plant.repository import PlantRepository
from app.plant.service import PlantService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_service(db) -> PlantService:
    return PlantService(db)


# ---------------------------------------------------------------------------
# create_plant
# ---------------------------------------------------------------------------

class TestCreatePlant:
    def test_creates_plant(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Fern", device_id="DEV001")
        assert plant.id is not None
        assert plant.name == "Fern"
        assert plant.device_id == "DEV001"

    def test_raises_if_device_already_registered(self, db):
        svc = make_service(db)
        svc.create_plant(name="Fern", device_id="DEV001")
        with pytest.raises(DeviceAlreadyRegistered):
            svc.create_plant(name="AnotherFern", device_id="DEV001")


# ---------------------------------------------------------------------------
# get_or_create_by_device
# ---------------------------------------------------------------------------

class TestGetOrCreateByDevice:
    def test_creates_new_plant_when_missing(self, db):
        svc = make_service(db)
        plant = svc.get_or_create_by_device("NEWDEV")
        assert plant.device_id == "NEWDEV"

    def test_returns_existing_plant(self, db):
        svc = make_service(db)
        existing = svc.create_plant(name="Cactus", device_id="DEV002")
        fetched = svc.get_or_create_by_device("DEV002")
        assert fetched.id == existing.id


# ---------------------------------------------------------------------------
# get_plant
# ---------------------------------------------------------------------------

class TestGetPlant:
    def test_returns_plant_by_id(self, db):
        svc = make_service(db)
        created = svc.create_plant(name="Basil", device_id="DEV003")
        fetched = svc.get_plant(created.id)
        assert fetched.name == "Basil"

    def test_raises_plant_not_found(self, db):
        svc = make_service(db)
        with pytest.raises(PlantNotFound):
            svc.get_plant(99999)


# ---------------------------------------------------------------------------
# list_plants
# ---------------------------------------------------------------------------

class TestListPlants:
    def test_empty_list(self, db):
        svc = make_service(db)
        assert svc.list_plants() == []

    def test_returns_all_plants(self, db):
        svc = make_service(db)
        svc.create_plant(name="A", device_id="D1")
        svc.create_plant(name="B", device_id="D2")
        plants = svc.list_plants()
        assert len(plants) == 2


# ---------------------------------------------------------------------------
# delete_plant
# ---------------------------------------------------------------------------

class TestDeletePlant:
    def test_deletes_plant(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Orchid", device_id="DEV004")
        plant_id = plant.id
        svc.delete_plant(plant_id)
        with pytest.raises(PlantNotFound):
            svc.get_plant(plant_id)

    def test_deletes_health_logs_too(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Orchid", device_id="DEV005")
        health_repo = HealthLogRepository(db)
        health_repo.create(
            plant_id=plant.id,
            image_paths=[],
            health_score=80,
            summary="Looks good",
            issues=[],
            suggestions=[],
        )
        db.flush()
        svc.delete_plant(plant.id)
        logs = health_repo.get_by_plant(plant.id)
        assert logs == []

    def test_raises_if_plant_not_found(self, db):
        svc = make_service(db)
        with pytest.raises(PlantNotFound):
            svc.delete_plant(99999)

    def test_cleans_up_image_file(self, db):
        svc = make_service(db)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                plant = svc.create_plant(name="Rose", device_id="DEV006")
                # Place a fake image
                fake_img = os.path.join(tmpdir, "rose.jpg")
                open(fake_img, "wb").close()
                plant.image_path = "rose.jpg"
                db.flush()
                svc.delete_plant(plant.id)
                assert not os.path.exists(fake_img)


# ---------------------------------------------------------------------------
# save_image
# ---------------------------------------------------------------------------

class TestSaveImage:
    def test_saves_valid_image(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Mint", device_id="DEV007")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                updated = svc.save_image(plant.id, b"fakeimage", "photo.jpg")
                assert updated.image_path is not None
                assert updated.image_path.endswith(".jpg")

    def test_raises_unsupported_format(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Mint2", device_id="DEV008")
        with pytest.raises(UnsupportedImageFormat):
            svc.save_image(plant.id, b"data", "photo.bmp")

    def test_raises_if_no_filename(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Mint3", device_id="DEV009")
        with pytest.raises(UnsupportedImageFormat):
            svc.save_image(plant.id, b"data", None)

    def test_raises_plant_not_found(self, db):
        svc = make_service(db)
        with pytest.raises(PlantNotFound):
            svc.save_image(99999, b"data", "photo.jpg")


# ---------------------------------------------------------------------------
# identify_species
# ---------------------------------------------------------------------------

class TestIdentifySpecies:
    @pytest.mark.asyncio
    async def test_raises_no_profile_image(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Unknown", device_id="DEV010")
        with pytest.raises(NoProfileImage):
            await svc.identify_species(plant.id)

    @pytest.mark.asyncio
    async def test_raises_no_openai_key(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Unknown2", device_id="DEV011")
        plant.image_path = "something.jpg"
        db.flush()
        with patch("app.plant.service.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.MEDIA_ROOT = "media"
            with pytest.raises(SpeciesIdentificationError):
                await svc.identify_species(plant.id)

    @pytest.mark.asyncio
    async def test_successful_identification(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Peace Lily", device_id="DEV012")
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_img = os.path.join(tmpdir, "plant.jpg")
            with open(fake_img, "wb") as f:
                f.write(b"fake")
            plant.image_path = "plant.jpg"
            db.flush()

            mock_response = MagicMock()
            mock_response.choices[0].message.content = (
                '{"species": "Peace Lily", "species_thai": "ลิลลี่", '
                '"confidence": "High", "care_guide": {"Watering": "weekly"}}'
            )

            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            with patch("app.plant.service.settings") as mock_settings, \
                 patch("app.plant.service.AsyncOpenAI", return_value=mock_client):
                mock_settings.OPENAI_API_KEY = "fake-key"
                mock_settings.MEDIA_ROOT = tmpdir
                result = await svc.identify_species(plant.id)
                assert result.species == "Peace Lily"
                assert result.confidence == "High"

    @pytest.mark.asyncio
    async def test_openai_exception_raises_species_error(self, db):
        svc = make_service(db)
        plant = svc.create_plant(name="Cactus", device_id="DEV013")
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_img = os.path.join(tmpdir, "cactus.jpg")
            open(fake_img, "wb").close()
            plant.image_path = "cactus.jpg"
            db.flush()

            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API down"))

            with patch("app.plant.service.settings") as mock_settings, \
                 patch("app.plant.service.AsyncOpenAI", return_value=mock_client):
                mock_settings.OPENAI_API_KEY = "fake-key"
                mock_settings.MEDIA_ROOT = tmpdir
                with pytest.raises(SpeciesIdentificationError):
                    await svc.identify_species(plant.id)
