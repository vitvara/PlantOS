"""Unit tests for PlantHealthService."""
from __future__ import annotations

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.health.exceptions import AnalysisError, TooManyImages
from app.health.service import PlantHealthService
from app.plant.service import PlantService


def make_health_svc(db) -> PlantHealthService:
    return PlantHealthService(db)


def make_plant(db, name="TestPlant", device_id="HD001"):
    svc = PlantService(db)
    return svc.create_plant(name=name, device_id=device_id)


# ---------------------------------------------------------------------------
# get_latest / get_history
# ---------------------------------------------------------------------------

class TestGetLatestAndHistory:
    def test_returns_none_when_no_logs(self, db):
        plant = make_plant(db)
        svc = make_health_svc(db)
        assert svc.get_latest(plant.id) is None

    def test_returns_empty_history(self, db):
        plant = make_plant(db)
        svc = make_health_svc(db)
        assert svc.get_history(plant.id) == []

    def test_returns_latest_log(self, db):
        plant = make_plant(db)
        svc = make_health_svc(db)
        log = svc.repo.create(
            plant_id=plant.id,
            image_paths=[],
            health_score=75,
            summary="Good",
            issues=[],
            suggestions=[],
        )
        db.flush()
        latest = svc.get_latest(plant.id)
        assert latest is not None
        assert latest.health_score == 75

    def test_history_returns_multiple_logs(self, db):
        plant = make_plant(db, device_id="HD002")
        svc = make_health_svc(db)
        for score in (60, 70, 80):
            svc.repo.create(
                plant_id=plant.id,
                image_paths=[],
                health_score=score,
                summary="ok",
                issues=[],
                suggestions=[],
            )
        db.flush()
        history = svc.get_history(plant.id)
        assert len(history) == 3


# ---------------------------------------------------------------------------
# analyze — validation errors
# ---------------------------------------------------------------------------

class TestAnalyzeValidation:
    @pytest.mark.asyncio
    async def test_raises_no_images(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD003")
        with pytest.raises(AnalysisError, match="At least one image"):
            await svc.analyze(plant_id=plant.id, images=[], filenames=[], species=None)

    @pytest.mark.asyncio
    async def test_raises_too_many_images(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD004")
        images = [b"img"] * 4
        filenames = ["a.jpg"] * 4
        with pytest.raises(TooManyImages):
            await svc.analyze(plant_id=plant.id, images=images, filenames=filenames)

    @pytest.mark.asyncio
    async def test_raises_no_openai_key(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD005")
        with patch("app.health.service.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.MEDIA_ROOT = "media"
            with pytest.raises(AnalysisError, match="OPENAI_API_KEY"):
                await svc.analyze(
                    plant_id=plant.id,
                    images=[b"img"],
                    filenames=["photo.jpg"],
                )


# ---------------------------------------------------------------------------
# analyze — success
# ---------------------------------------------------------------------------

class TestAnalyzeSuccess:
    @pytest.mark.asyncio
    async def test_creates_health_log(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD006")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"health_score": 85, "summary": "Healthy plant", '
            '"issues": [], "suggestions": ["Water more"]}'
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("app.health.service.settings") as mock_settings, \
             patch("app.health.service.AsyncOpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "fake-key"
            mock_settings.MEDIA_ROOT = tmpdir
            log = await svc.analyze(
                plant_id=plant.id,
                images=[b"fakedata"],
                filenames=["leaf.jpg"],
                species="Peace Lily",
            )
        assert log.health_score == 85
        assert log.summary == "Healthy plant"
        assert "Water more" in log.suggestions

    @pytest.mark.asyncio
    async def test_clamps_score_to_0_100(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD007")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"health_score": 150, "summary": "Overscored", "issues": [], "suggestions": []}'
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("app.health.service.settings") as mock_settings, \
             patch("app.health.service.AsyncOpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "fake-key"
            mock_settings.MEDIA_ROOT = tmpdir
            log = await svc.analyze(
                plant_id=plant.id,
                images=[b"data"],
                filenames=["photo.png"],
            )
        assert log.health_score == 100

    @pytest.mark.asyncio
    async def test_openai_failure_raises_analysis_error(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD008")

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("fail"))

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("app.health.service.settings") as mock_settings, \
             patch("app.health.service.AsyncOpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "fake-key"
            mock_settings.MEDIA_ROOT = tmpdir
            with pytest.raises(AnalysisError):
                await svc.analyze(
                    plant_id=plant.id,
                    images=[b"data"],
                    filenames=["photo.jpg"],
                )

    @pytest.mark.asyncio
    async def test_analyze_without_species_context(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD009")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"health_score": 50, "summary": "Fair", "issues": ["yellow leaves"], "suggestions": []}'
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("app.health.service.settings") as mock_settings, \
             patch("app.health.service.AsyncOpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "fake-key"
            mock_settings.MEDIA_ROOT = tmpdir
            log = await svc.analyze(
                plant_id=plant.id,
                images=[b"data"],
                filenames=["photo.jpg"],
                species=None,
            )
        assert log.health_score == 50

    @pytest.mark.asyncio
    async def test_analyze_with_unknown_species(self, db):
        svc = make_health_svc(db)
        plant = make_plant(db, device_id="HD010")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"health_score": 60, "summary": "ok", "issues": [], "suggestions": []}'
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("app.health.service.settings") as mock_settings, \
             patch("app.health.service.AsyncOpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "fake-key"
            mock_settings.MEDIA_ROOT = tmpdir
            log = await svc.analyze(
                plant_id=plant.id,
                images=[b"data"],
                filenames=["photo.webp"],
                species="Unknown",
            )
        assert log.health_score == 60
