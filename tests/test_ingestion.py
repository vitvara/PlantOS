"""Integration tests for the sensor ingestion API endpoint."""
from __future__ import annotations

import pytest


VALID_PAYLOAD = {
    "device_id": "ESP32_TEST",
    "temperature": 24.5,
    "humidity": 60.0,
    "soil_moisture": 45.0,
}

VALID_HEADERS = {"X-API-Key": "supersecretkey"}


class TestIngestEndpoint:
    def test_valid_ingest_returns_202(self, client):
        response = client.post("/api/ingest", json=VALID_PAYLOAD, headers=VALID_HEADERS)
        assert response.status_code == 202
        data = response.json()
        assert data["device_id"] == "ESP32_TEST"
        assert data["status"] == "accepted"
        assert "timestamp" in data

    def test_only_temperature(self, client):
        payload = {"device_id": "ESP32_TEMP", "temperature": 22.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 202

    def test_only_humidity(self, client):
        payload = {"device_id": "ESP32_HUM", "humidity": 55.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 202

    def test_only_soil_moisture(self, client):
        payload = {"device_id": "ESP32_SOIL", "soil_moisture": 40.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 202

    def test_invalid_api_key_returns_401(self, client):
        response = client.post(
            "/api/ingest",
            json=VALID_PAYLOAD,
            headers={"X-API-Key": "wrongkey"},
        )
        assert response.status_code == 401

    def test_missing_api_key_returns_422(self, client):
        response = client.post("/api/ingest", json=VALID_PAYLOAD)
        assert response.status_code == 422

    def test_all_fields_none_returns_400(self, client):
        payload = {"device_id": "ESP32_EMPTY"}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 400

    def test_device_id_with_space_returns_422(self, client):
        payload = {"device_id": "ESP 32", "temperature": 22.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 422

    def test_device_id_too_short_returns_422(self, client):
        payload = {"device_id": "AB", "temperature": 22.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 422

    def test_temperature_out_of_range_returns_422(self, client):
        payload = {"device_id": "DEV001", "temperature": 200.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 422

    def test_humidity_out_of_range_returns_422(self, client):
        payload = {"device_id": "DEV001", "humidity": 150.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 422

    def test_ingest_auto_creates_plant(self, client):
        # Ingestion should auto-register the device as a plant
        payload = {"device_id": "AUTODEV", "temperature": 25.0}
        response = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 202

    def test_multiple_ingests_same_device(self, client):
        payload = {"device_id": "MULTIDEV", "temperature": 25.0}
        for _ in range(3):
            r = client.post("/api/ingest", json=payload, headers=VALID_HEADERS)
            assert r.status_code == 202
