"""Integration tests for UI routes (Jinja2 HTML views)."""
from __future__ import annotations

import io
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_plant_via_api(client, name="Fern", device_id="UI001"):
    r = client.post("/plants/", json={"name": name, "device_id": device_id})
    return r.json()


# ---------------------------------------------------------------------------
# Home redirect
# ---------------------------------------------------------------------------

class TestHomeRoute:
    def test_redirects_to_catalog(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/catalog" in response.headers["location"]


# ---------------------------------------------------------------------------
# Catalog page
# ---------------------------------------------------------------------------

class TestCatalogRoute:
    def test_catalog_renders(self, client):
        response = client.get("/catalog")
        assert response.status_code == 200
        assert b"html" in response.content.lower()

    def test_catalog_shows_plants(self, client):
        create_plant_via_api(client, "Rose", "UI010")
        response = client.get("/catalog")
        assert response.status_code == 200
        assert b"Rose" in response.content

    def test_catalog_with_error_param(self, client):
        response = client.get("/catalog?error=Something+went+wrong")
        assert response.status_code == 200
        assert b"Something went wrong" in response.content

    def test_catalog_with_success_param(self, client):
        response = client.get("/catalog?success=Plant+deleted")
        assert response.status_code == 200
        assert b"Plant deleted" in response.content


# ---------------------------------------------------------------------------
# Register plant via UI form
# ---------------------------------------------------------------------------

class TestRegisterPlantUI:
    def test_register_redirects_to_detail(self, client):
        response = client.post(
            "/catalog/register",
            data={"name": "Orchid", "device_id": "UI020"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/catalog/" in response.headers["location"]

    def test_register_duplicate_redirects_with_error(self, client):
        client.post("/catalog/register", data={"name": "A", "device_id": "UI021"})
        response = client.post(
            "/catalog/register",
            data={"name": "B", "device_id": "UI021"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "error" in response.headers["location"]


# ---------------------------------------------------------------------------
# Plant detail page
# ---------------------------------------------------------------------------

class TestPlantDetailRoute:
    def test_detail_renders(self, client):
        plant = create_plant_via_api(client, "Basil", "UI030")
        response = client.get(f"/catalog/{plant['id']}")
        assert response.status_code == 200
        assert b"Basil" in response.content

    def test_detail_404_for_missing(self, client):
        response = client.get("/catalog/99999")
        assert response.status_code == 404

    def test_detail_with_error_param(self, client):
        plant = create_plant_via_api(client, "Basil2", "UI031")
        response = client.get(f"/catalog/{plant['id']}?error=oops")
        assert response.status_code == 200
        assert b"oops" in response.content

    def test_detail_with_success_param(self, client):
        plant = create_plant_via_api(client, "Basil3", "UI032")
        response = client.get(f"/catalog/{plant['id']}?success=done")
        assert response.status_code == 200
        assert b"done" in response.content


# ---------------------------------------------------------------------------
# Delete plant via UI
# ---------------------------------------------------------------------------

class TestDeletePlantUI:
    def test_delete_redirects_with_success(self, client):
        plant = create_plant_via_api(client, "Mint", "UI040")
        response = client.post(
            f"/catalog/{plant['id']}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "success" in response.headers["location"]

    def test_delete_nonexistent_returns_404(self, client):
        response = client.post("/catalog/99999/delete")
        assert response.status_code == 404

    def test_delete_also_removes_health_logs(self, client, db):
        from app.health.repository import HealthLogRepository
        plant = create_plant_via_api(client, "Cactus", "UI041")
        health_repo = HealthLogRepository(db)
        health_repo.create(
            plant_id=plant["id"],
            image_paths=[],
            health_score=70,
            summary="ok",
            issues=[],
            suggestions=[],
        )
        db.flush()
        response = client.post(
            f"/catalog/{plant['id']}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 303
        logs = health_repo.get_by_plant(plant["id"])
        assert logs == []


# ---------------------------------------------------------------------------
# Upload plant image via UI
# ---------------------------------------------------------------------------

class TestUploadPlantImageUI:
    def test_upload_valid_image_redirects(self, client):
        plant = create_plant_via_api(client, "Lily", "UI050")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"fakedata")
                response = client.post(
                    f"/catalog/{plant['id']}/image",
                    files={"file": ("photo.jpg", fake_file, "image/jpeg")},
                    follow_redirects=False,
                )
        assert response.status_code == 303

    def test_upload_bad_format_redirects_with_error(self, client):
        plant = create_plant_via_api(client, "Lily2", "UI051")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"data")
                response = client.post(
                    f"/catalog/{plant['id']}/image",
                    files={"file": ("photo.bmp", fake_file, "image/bmp")},
                    follow_redirects=False,
                )
        assert response.status_code == 303
        assert "error" in response.headers["location"]

    def test_upload_missing_plant_returns_404(self, client):
        fake_file = io.BytesIO(b"data")
        response = client.post(
            "/catalog/99999/image",
            files={"file": ("photo.jpg", fake_file, "image/jpeg")},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Identify species via UI
# ---------------------------------------------------------------------------

class TestIdentifySpeciesUI:
    def test_no_image_redirects_with_error(self, client):
        plant = create_plant_via_api(client, "Unknown", "UI060")
        response = client.post(
            f"/catalog/{plant['id']}/identify-species",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "error" in response.headers["location"]

    def test_success_redirects_with_success(self, client):
        plant = create_plant_via_api(client, "Peace", "UI061")
        with tempfile.TemporaryDirectory() as tmpdir:
            # Upload image first
            with patch("app.plant.service.settings") as ms:
                ms.MEDIA_ROOT = tmpdir
                ms.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"fakedata")
                client.post(
                    f"/catalog/{plant['id']}/image",
                    files={"file": ("plant.jpg", fake_file, "image/jpeg")},
                )

            mock_response = MagicMock()
            mock_response.choices[0].message.content = (
                '{"species":"Peace Lily","species_thai":"ลิลลี่",'
                '"confidence":"High","care_guide":{"Watering":"weekly"}}'
            )
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            with patch("app.plant.service.settings") as ms2, \
                 patch("app.plant.service.AsyncOpenAI", return_value=mock_client):
                ms2.OPENAI_API_KEY = "fake-key"
                ms2.MEDIA_ROOT = tmpdir
                response = client.post(
                    f"/catalog/{plant['id']}/identify-species",
                    follow_redirects=False,
                )
        assert response.status_code == 303
        assert "success" in response.headers["location"]

    def test_openai_error_redirects_with_error(self, client):
        plant = create_plant_via_api(client, "Cactus", "UI062")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as ms:
                ms.MEDIA_ROOT = tmpdir
                ms.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"fakedata")
                client.post(
                    f"/catalog/{plant['id']}/image",
                    files={"file": ("cactus.jpg", fake_file, "image/jpeg")},
                )

            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("fail"))

            with patch("app.plant.service.settings") as ms2, \
                 patch("app.plant.service.AsyncOpenAI", return_value=mock_client):
                ms2.OPENAI_API_KEY = "fake-key"
                ms2.MEDIA_ROOT = tmpdir
                response = client.post(
                    f"/catalog/{plant['id']}/identify-species",
                    follow_redirects=False,
                )
        assert response.status_code == 303
        assert "error" in response.headers["location"]

    def test_plant_not_found_returns_404(self, client):
        response = client.post("/catalog/99999/identify-species")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Health timeline page
# ---------------------------------------------------------------------------

class TestHealthTimelineRoute:
    def test_timeline_renders(self, client):
        plant = create_plant_via_api(client, "Fern", "UI070")
        response = client.get(f"/catalog/{plant['id']}/health")
        assert response.status_code == 200

    def test_timeline_404_for_missing(self, client):
        response = client.get("/catalog/99999/health")
        assert response.status_code == 404

    def test_timeline_with_error_param(self, client):
        plant = create_plant_via_api(client, "Fern2", "UI071")
        response = client.get(f"/catalog/{plant['id']}/health?error=bad")
        assert response.status_code == 200
        assert b"bad" in response.content


# ---------------------------------------------------------------------------
# Health analysis submission via UI
# ---------------------------------------------------------------------------

class TestHealthAnalysisUI:
    def test_no_files_redirects_with_error(self, client):
        plant = create_plant_via_api(client, "Test", "UI080")
        response = client.post(
            f"/catalog/{plant['id']}/health/analyze",
            files=[],
            follow_redirects=False,
        )
        assert response.status_code in (303, 422)

    def test_plant_not_found_returns_404(self, client):
        fake_file = io.BytesIO(b"data")
        response = client.post(
            "/catalog/99999/health/analyze",
            files={"files": ("photo.jpg", fake_file, "image/jpeg")},
        )
        assert response.status_code == 404

    def test_analysis_success_redirects(self, client):
        plant = create_plant_via_api(client, "Healthy", "UI081")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"health_score": 90, "summary": "Excellent", "issues": [], "suggestions": []}'
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("app.health.service.settings") as ms, \
             patch("app.health.service.AsyncOpenAI", return_value=mock_client):
            ms.OPENAI_API_KEY = "fake-key"
            ms.MEDIA_ROOT = tmpdir
            fake_file = io.BytesIO(b"fakedata")
            response = client.post(
                f"/catalog/{plant['id']}/health/analyze",
                files={"files": ("leaf.jpg", fake_file, "image/jpeg")},
                follow_redirects=False,
            )
        assert response.status_code == 303

    def test_too_many_images_redirects_with_error(self, client):
        plant = create_plant_via_api(client, "Overfed", "UI082")
        with patch("app.health.service.settings") as ms:
            ms.OPENAI_API_KEY = "fake-key"
            ms.MEDIA_ROOT = "media"
            files = [
                ("files", (f"img{i}.jpg", io.BytesIO(b"data"), "image/jpeg"))
                for i in range(4)
            ]
            response = client.post(
                f"/catalog/{plant['id']}/health/analyze",
                files=files,
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert "error" in response.headers["location"]


# ---------------------------------------------------------------------------
# Sensor data JSON endpoint
# ---------------------------------------------------------------------------

class TestSensorDataEndpoint:
    def test_returns_json_for_valid_plant(self, client):
        plant = create_plant_via_api(client, "SensorPlant", "UI090")
        response = client.get(f"/catalog/{plant['id']}/sensor-data")
        assert response.status_code == 200
        data = response.json()
        assert "device_id" in data
        assert data["device_id"] == "UI090"
        assert "points" in data
        assert isinstance(data["points"], list)

    def test_returns_empty_points_when_no_data(self, client):
        plant = create_plant_via_api(client, "Empty", "UI091")
        response = client.get(f"/catalog/{plant['id']}/sensor-data?hours=24")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["points"] == []

    def test_404_for_missing_plant(self, client):
        response = client.get("/catalog/99999/sensor-data")
        assert response.status_code == 404

    def test_default_hours_is_24(self, client):
        plant = create_plant_via_api(client, "HoursCheck", "UI092")
        response = client.get(f"/catalog/{plant['id']}/sensor-data")
        assert response.status_code == 200
        data = response.json()
        assert data["hours"] == 24.0

    def test_custom_hours_param(self, client):
        plant = create_plant_via_api(client, "CustomH", "UI093")
        response = client.get(f"/catalog/{plant['id']}/sensor-data?hours=1")
        assert response.status_code == 200
        assert response.json()["hours"] == 1.0

    def test_hours_too_small_returns_422(self, client):
        plant = create_plant_via_api(client, "TooSmall", "UI094")
        response = client.get(f"/catalog/{plant['id']}/sensor-data?hours=0.1")
        assert response.status_code == 422

    def test_hours_too_large_returns_422(self, client):
        plant = create_plant_via_api(client, "TooLarge", "UI095")
        response = client.get(f"/catalog/{plant['id']}/sensor-data?hours=999")
        assert response.status_code == 422

    def test_points_contain_expected_fields(self, client, db):
        from app.ingestion.repository import SensorDataRepository
        from app.ingestion.schemas import SensorIngestRequest
        plant = create_plant_via_api(client, "WithData", "UI096")
        repo = SensorDataRepository(db)
        repo.create(SensorIngestRequest(device_id="UI096", temperature=22.5, humidity=60.0, soil_moisture=40.0))
        db.flush()
        response = client.get(f"/catalog/{plant['id']}/sensor-data?hours=24")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        pt = data["points"][0]
        assert "t" in pt
        assert "temp" in pt
        assert "hum" in pt
        assert "soil" in pt
        assert pt["temp"] == 22.5
        assert pt["hum"] == 60.0
        assert pt["soil"] == 40.0
