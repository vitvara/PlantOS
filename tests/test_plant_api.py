"""Integration tests for the Plant REST API routes (v1)."""
from __future__ import annotations

import io
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def create_plant(client, name="Fern", device_id="DEV_API_01"):
    response = client.post("/api/v1/plants/", json={"name": name, "device_id": device_id})
    assert response.status_code == 201
    return response.json()


class TestCreatePlantEndpoint:
    def test_create_plant_returns_201(self, client):
        response = client.post("/api/v1/plants/", json={"name": "Fern", "device_id": "AP001"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Fern"
        assert data["device_id"] == "AP001"

    def test_duplicate_device_id_returns_409(self, client):
        client.post("/api/v1/plants/", json={"name": "A", "device_id": "AP002"})
        response = client.post("/api/v1/plants/", json={"name": "B", "device_id": "AP002"})
        assert response.status_code == 409

    def test_missing_name_returns_422(self, client):
        response = client.post("/api/v1/plants/", json={"device_id": "AP003"})
        assert response.status_code == 422


class TestListPlantsEndpoint:
    def test_list_empty(self, client):
        response = client.get("/api/v1/plants/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_multiple(self, client):
        create_plant(client, "A", "AP010")
        create_plant(client, "B", "AP011")
        response = client.get("/api/v1/plants/")
        assert response.status_code == 200
        assert len(response.json()) == 2


class TestGetPlantEndpoint:
    def test_get_existing_plant(self, client):
        plant = create_plant(client, "Rose", "AP020")
        response = client.get(f"/api/v1/plants/{plant['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "Rose"

    def test_get_nonexistent_returns_404(self, client):
        response = client.get("/api/v1/plants/99999")
        assert response.status_code == 404


class TestUploadImageEndpoint:
    def test_upload_valid_image(self, client):
        plant = create_plant(client, "Lily", "AP030")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"fakeimagedata")
                response = client.post(
                    f"/api/v1/plants/{plant['id']}/upload-image",
                    files={"file": ("photo.jpg", fake_file, "image/jpeg")},
                )
        assert response.status_code == 200
        assert response.json()["image_path"] is not None

    def test_upload_unsupported_format(self, client):
        plant = create_plant(client, "Lily2", "AP031")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"data")
                response = client.post(
                    f"/api/v1/plants/{plant['id']}/upload-image",
                    files={"file": ("photo.bmp", fake_file, "image/bmp")},
                )
        assert response.status_code == 400

    def test_upload_plant_not_found(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                fake_file = io.BytesIO(b"data")
                response = client.post(
                    "/api/v1/plants/99999/upload-image",
                    files={"file": ("photo.jpg", fake_file, "image/jpeg")},
                )
        assert response.status_code == 404


class TestIdentifySpeciesEndpoint:
    @pytest.mark.asyncio
    async def test_no_profile_image_returns_422(self, client):
        plant = create_plant(client, "Unknown", "AP040")
        response = client.post(f"/api/v1/plants/{plant['id']}/identify-species")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_identify_species_success(self, client):
        plant = create_plant(client, "Peace Lily", "AP041")
        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            fake_img = os.path.join(tmpdir, "plant.jpg")
            open(fake_img, "wb").write(b"fake")
            # Manually set image_path via upload first
            with patch("app.plant.service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmpdir
                mock_settings.OPENAI_API_KEY = ""
                fake_file = io.BytesIO(b"fakedata")
                client.post(
                    f"/api/v1/plants/{plant['id']}/upload-image",
                    files={"file": ("plant.jpg", fake_file, "image/jpeg")},
                )

            mock_ai = AsyncMock()
            mock_ai.complete = AsyncMock(return_value=(
                '{"species":"Peace Lily","species_thai":"ลิลลี่",'
                '"confidence":"High","care_guide":{"Watering":"weekly"}}'
            ))

            with patch("app.plant.service.settings") as mock_settings2, \
                 patch("app.core.protocols.OpenAIProvider", return_value=mock_ai):
                mock_settings2.MEDIA_ROOT = tmpdir
                response = client.post(f"/api/v1/plants/{plant['id']}/identify-species")
        assert response.status_code == 200

    def test_identify_species_plant_not_found(self, client):
        response = client.post("/api/v1/plants/99999/identify-species")
        assert response.status_code == 404
