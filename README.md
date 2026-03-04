# 🌿 PlantOS

An AI-powered IoT plant monitoring platform. Connect ESP32 sensor devices to your plants, track temperature, humidity, and soil moisture in real time, and use GPT-4 vision to identify species and assess plant health — all from a clean, mobile-friendly web interface.

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-green?style=flat-square&logo=fastapi)
![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey?style=flat-square&logo=sqlite)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?style=flat-square&logo=openai)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker)
![Tests](https://img.shields.io/badge/tests-128%20passed-brightgreen?style=flat-square&logo=pytest)
![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen?style=flat-square)

<img width="320" height="699" alt="image" src="https://github.com/user-attachments/assets/c841d8ad-273a-4643-b806-e16b77e1eca2" />
<img width="1904" height="973" alt="image" src="https://github.com/user-attachments/assets/e93c5682-7152-48ea-9e6c-907334d82aec" />
<img width="1894" height="968" alt="image" src="https://github.com/user-attachments/assets/6696d955-7ac3-4ddf-8367-f4f806bcfed4" />

---

## Features

| Feature | Description |
|---|---
| 🌿 **Plant Catalog** | Register and manage all your plants with profile photos |
| 📡 **Sensor Ingestion** | Receive temperature, humidity & soil moisture from ESP32 devices |
| 📊 **Live Dashboard** | Real-time sensor readings with time-series charts |
| 🔬 **Species ID** | Auto-identify plant species from a photo using GPT-4 vision |
| ❤️ **Health Analysis** | Score plant health 0–100 and get AI-generated issues & suggestions |
| 📱 **Mobile Ready** | iPhone-optimized with bottom tab navigation and touch-friendly UI |
| 🗂️ **Smart Catalog** | Search, filter, and see status tags (photo / species / sensors / health) per plant |
| 🗑️ **Safe Delete** | Delete plants with a name-confirmation modal — no accidental removals |

---

## Tech Stack

- **Backend:** FastAPI · SQLAlchemy 2.0 · SQLite · Python 3.11+
- **AI:** OpenAI GPT-4.1 (species ID) · GPT-4o (health analysis)
- **Frontend:** Jinja2 templates · Chart.js · CSS custom properties · Inter font
- **Package manager:** [uv](https://github.com/astral-sh/uv)
- **Containerisation:** Docker (dev + release Dockerfiles)

---

## Project Structure

```
plantos/
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── lifespan.py          # Startup / shutdown hooks
│   ├── core/
│   │   ├── config.py        # Settings (Pydantic)
│   │   └── database.py      # SQLAlchemy engine & session
│   ├── api/
│   │   ├── router.py        # Root API router
│   │   └── deps.py          # FastAPI dependency factories
│   ├── ingestion/           # ESP32 sensor data pipeline
│   ├── plant/               # Plant CRUD + species identification
│   ├── health/              # AI health analysis logs
│   ├── ui/                  # Jinja2 server-rendered web UI
│   └── templates/           # HTML templates
│       ├── base.html
│       ├── catalog.html
│       ├── plant_detail.html
│       └── health_timeline.html
├── media/                   # Uploaded photos (git-ignored)
├── plant.db                 # SQLite database (git-ignored)
├── .env                     # Secrets — never commit this (git-ignored)
├── .env.example             # Safe template to commit
├── Dockerfile               # Dev image
├── DockerfileRelease        # Production image
├── pyproject.toml
└── uv.lock
```

---

## Quick Start

### Prerequisites

- Python 3.11+ **or** Docker
- [uv](https://github.com/astral-sh/uv) package manager
- An [OpenAI API key](https://platform.openai.com/api-keys)

### 1. Clone & configure

```bash
git clone https://github.com/your-username/plantos.git
cd plantos

cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Run locally

```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

### 3. Run with Docker

```bash
# Development (with live reload)
docker build -f Dockerfile -t plantos:dev .
docker run -p 8000:8000 --env-file .env \
  -v $(pwd)/plant.db:/app/plant.db \
  -v $(pwd)/media:/app/media \
  plantos:dev uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production
docker build -f DockerfileRelease -t plantos:latest .
docker run -p 8000:8000 --env-file .env \
  -v $(pwd)/plant.db:/app/plant.db \
  -v $(pwd)/media:/app/media \
  plantos:latest
```

---

## Configuration

Create a `.env` file (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `DATABASE_URL` | `sqlite:///./plant.db` | SQLAlchemy database URL |
| `MEDIA_ROOT` | `media/` | Directory for uploaded images |
| `API_KEY` | `supersecretkey` | `X-API-Key` header value for ESP32 devices |

> ⚠️ **Never commit your `.env` file.** It is excluded by `.gitignore`.

---

## ESP32 Integration

Send sensor readings via HTTP POST:

```
POST /api/ingest
X-API-Key: supersecretkey
Content-Type: application/json

{
  "device_id": "ESP32_A1B2",
  "temperature": 24.5,
  "humidity": 62.0,
  "soil_moisture": 45.0
}
```

All three sensor fields are optional — send only what your hardware supports. If the `device_id` is not yet registered, the plant is auto-created in the catalog.

**Minimal Arduino/ESP32 sketch:**

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* SERVER    = "http://your-server:8000/api/ingest";
const char* API_KEY   = "supersecretkey";
const char* DEVICE_ID = "ESP32_A1B2";

void sendReading(float temp, float hum, float soil) {
  HTTPClient http;
  http.begin(SERVER);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);

  StaticJsonDocument<200> doc;
  doc["device_id"]     = DEVICE_ID;
  doc["temperature"]   = temp;
  doc["humidity"]      = hum;
  doc["soil_moisture"] = soil;

  String body;
  serializeJson(doc, body);
  http.POST(body);
  http.end();
}
```

---

## API Reference

### Sensor Ingestion

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/ingest` | `X-API-Key` | Ingest sensor data from a device |

### Plant Management

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/plants/` | Create a plant |
| `GET` | `/plants/` | List all plants |
| `GET` | `/plants/{id}` | Get plant details |
| `POST` | `/plants/{id}/upload-image` | Upload profile photo |
| `POST` | `/plants/{id}/identify-species` | Trigger AI species identification |

### Health Analysis

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/plants/{id}/health` | Submit photos for health analysis |
| `GET` | `/plants/{id}/health` | Get health history |

### Web UI Routes

| Route | Description |
|---|---|
| `GET /catalog` | Plant catalog with search & status tags |
| `GET /catalog/{id}` | Plant detail with live readings, chart, care guide |
| `GET /catalog/{id}/health` | Health timeline with score trend |

Interactive API docs are available at `/docs` (Swagger UI) and `/redoc`.

---

## Screenshots

> Add screenshots here after first deployment.

| Catalog | Plant Detail | Health Timeline |
|---|---|---|
| *(screenshot)* | *(screenshot)* | *(screenshot)* |

---

## Tests

Run the test suite:

```bash
uv run pytest tests/ --cov=app --cov-report=term-missing
```

**128 tests · 95% coverage**

| Module | Stmts | Miss | Cover |
|---|---|---|---|
| `app/api/deps.py` | 17 | 0 | **100%** |
| `app/api/router.py` | 10 | 0 | **100%** |
| `app/core/config.py` | 15 | 0 | **100%** |
| `app/core/database.py` | 28 | 9 | 68% |
| `app/health/repository.py` | 22 | 0 | **100%** |
| `app/health/routes.py` | 30 | 17 | 43% |
| `app/health/service.py` | 65 | 1 | 98% |
| `app/ingestion/repository.py` | 15 | 0 | **100%** |
| `app/ingestion/routes.py` | 14 | 0 | **100%** |
| `app/ingestion/service.py` | 21 | 0 | **100%** |
| `app/lifespan.py` | 19 | 1 | 95% |
| `app/main.py` | 27 | 0 | **100%** |
| `app/plant/repository.py` | 40 | 0 | **100%** |
| `app/plant/routes.py` | 41 | 2 | 95% |
| `app/plant/service.py` | 89 | 3 | 97% |
| `app/ui/repository.py` | 20 | 0 | **100%** |
| `app/ui/routes.py` | 108 | 1 | 99% |
| `app/ui/service.py` | 30 | 0 | **100%** |
| **TOTAL** | **721** | **34** | **95%** |

---

## Roadmap / TODO

### 🧪 Tests
- [x] Set up `pytest` with `httpx` test client — 128 tests, 95% coverage
- [x] Unit tests for `PlantService` — create, delete, identify species
- [x] Unit tests for `HealthService` — analyze, health scoring thresholds
- [x] Integration tests for `POST /api/ingest` (valid key, invalid key, missing fields)
- [x] Integration tests for plant registration and delete flow
- [x] Template rendering smoke tests (context keys render without error)
- [x] Mock OpenAI responses in tests to avoid API costs and flakiness
- [ ] GitHub Actions CI — run tests automatically on every PR

### 🔒 Security
- [ ] Per-device API keys stored in DB (replace shared `supersecretkey`)
- [ ] Rate limiting on `/api/ingest` (e.g. 1 req/min per device)
- [ ] Login page for the web UI (session-based or OAuth)
- [ ] File size & MIME-type validation on image uploads
- [ ] HTTPS guide — Caddy or nginx reverse proxy with Let's Encrypt

### ✨ New Features
- [ ] **Dashboard page** — multi-plant sensor overview with side-by-side charts
- [ ] **WebSocket live updates** — real-time sensor values without page refresh
- [ ] **Push notifications** — alert when health score drops or soil is too dry
- [ ] **Watering log** — record watering events and display on health timeline
- [ ] **Auto health schedule** — trigger AI analysis on a cron/interval
- [ ] **Data export** — download sensor history as CSV or JSON
- [ ] **Light sensor support** — add LDR/lux sensor to ingest pipeline
- [ ] **CO₂ / air quality** — extend sensor model for MQ-135 / SCD30
- [ ] **Multi-language toggle** — Thai / English (species data already has Thai names)
- [ ] **Shareable plant page** — public read-only URL per plant
- [ ] **Photo gallery** — browse all uploaded photos per plant in a lightbox grid
- [ ] **Plant rename / edit** — inline edit name and device ID from detail page

### 🏗️ Infrastructure
- [ ] `docker-compose.yml` with named volumes for `media/` and `plant.db`
- [ ] `docker-compose.prod.yml` with Caddy + TLS
- [ ] GitHub Actions CI — lint (`ruff`), type-check (`mypy`), tests on every PR
- [ ] Dependabot for automated dependency updates
- [ ] Alembic migrations (replace `create_all` on startup)
- [ ] Structured JSON logging with request IDs
- [ ] `GET /health` liveness endpoint
- [ ] Prometheus metrics via `prometheus-fastapi-instrumentator`

### 🎨 UI / UX
- [ ] Dark mode toggle with `prefers-color-scheme` auto-default
- [ ] Drag-and-drop photo upload zones
- [ ] Inline sparkline on catalog cards (last 24 h soil moisture)
- [ ] Offline-capable PWA — service worker + `manifest.json`
- [ ] Swipe-to-refresh on mobile catalog

---

## Contributing

1. Fork the repo and create a branch: `git checkout -b feat/your-feature`
2. Make your changes and verify the server starts: `uv run uvicorn app.main:app --reload`
3. Open a Pull Request with a clear description of what and why

Please keep PRs focused — one feature or fix per PR.

---

## License

MIT © 2025
