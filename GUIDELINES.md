# PlantOS Development Guidelines

## Architecture Overview

PlantOS follows a strict **3-layer architecture**. Every domain (plant, health, ingestion, ui) has the same shape:

```
HTTP Request
    ↓
app/api/v1/<domain>.py   — Route layer     (HTTP in, HTTP out)
    ↓
app/<domain>/service.py  — Service layer   (business logic)
    ↓
app/<domain>/repository.py — Repository layer (DB queries)
    ↓
Database (SQLite / MySQL)
```

---

## Layer Responsibilities

### Route layer (`app/api/v1/` or `app/ui/routes.py`)
- Parse and validate HTTP input (path params, query params, request body, file uploads)
- Call one or more service methods
- Map domain exceptions → HTTP status codes
- Return JSON response or Jinja2 template

**Does NOT:**
- Contain business logic
- Query the database directly
- Know about SQLAlchemy models

### Service layer (`app/<domain>/service.py`)
- Own all business rules and validation
- Orchestrate calls to repositories and external services (AI, storage)
- Raise domain-specific exceptions (`app/<domain>/exceptions.py`)
- Accept dependencies via constructor (DB session, AI provider)

**Does NOT:**
- Import `Request`, `Response`, `HTTPException`, or FastAPI types
- Build HTTP responses
- Query the database directly (delegates to repository)

### Repository layer (`app/<domain>/repository.py`)
- Issue all SQL queries via SQLAlchemy ORM
- Return ORM model instances (never raw dicts or tuples)
- No business logic — just CRUD

**Does NOT:**
- Know about HTTP or services
- Raise HTTP exceptions
- Contain conditional business logic

---

## Adding a New Domain Module

Checklist when adding a new domain (e.g., `notifications`):

1. `app/notifications/` — create the package directory
2. `app/notifications/models.py` — SQLAlchemy ORM model
3. `app/notifications/schemas.py` — Pydantic request/response schemas
4. `app/notifications/exceptions.py` — domain-specific exception classes
5. `app/notifications/repository.py` — DB query methods
6. `app/notifications/service.py` — business logic class
7. `app/api/v1/notifications.py` — REST endpoints
8. Register the router in `app/api/v1/router.py`
9. Add `ServiceFactory.notifications_service()` in `app/core/factory.py`
10. Add `get_notifications_service()` dependency in `app/api/deps.py`
11. Add tests in `tests/test_notifications_*.py`

---

## Docstring Templates

### Module docstring
```python
"""
Brief one-line summary.

Responsibilities
----------------
* What this module IS responsible for.
* Another responsibility.

Not responsible for
-------------------
* What this module delegates elsewhere.

Typical usage
-------------
::

    from app.plant.service import PlantService
    svc = PlantService(db=session, ai=provider)
    plant = await svc.identify_species(plant_id=1)
"""
```

### Class docstring
```python
class PlantService:
    """
    Orchestrates plant domain business logic.

    Responsibilities:
        - Plant registration and CRUD
        - Profile image management
        - Species identification via AI provider

    Not responsible for:
        - HTTP concerns (use routes layer)
        - Direct DB queries (use PlantRepository)

    Args:
        db: SQLAlchemy Session injected by FastAPI dependency.
        ai: AI provider for species identification. When ``None`` the
            service creates its own OpenAI client (legacy behaviour).
    """
```

### Function / method docstring
```python
async def identify_species(self, plant_id: int) -> Plant:
    """
    Identify plant species from profile photo using AI.

    Brief description of what the method does and how.

    Args:
        plant_id: Database ID of the plant to identify.

    Returns:
        Updated Plant ORM instance with species, species_thai,
        confidence, care_guide, and species_identified_at set.

    Raises:
        PlantNotFound: If no plant with plant_id exists.
        NoProfileImage: If the plant has no uploaded profile photo.
        SpeciesIdentificationError: If AI call fails or returns
                                    unparseable JSON.
    """
```

---

## Logging

Use `get_logger(__name__)` at module level. Never use `print()`.

```python
from app.core.logging import get_logger, log_call

logger = get_logger(__name__)

# Structured key-value logging
logger.info("Plant registered", plant_id=42, device_id="esp-01")
logger.warning("Image missing", plant_id=7)
logger.error("AI call failed", error=str(exc), plant_id=42)

# Automatic entry/exit/duration/error logging via decorator
@log_call(logger)
async def identify_species(self, plant_id: int) -> Plant: ...
```

Log levels:
- `debug` — verbose internals (disabled in production)
- `info` — normal operations (plant created, image uploaded)
- `warning` — recoverable unexpected state
- `error` — operation failed, exception raised

---

## Error Handling

### Domain exceptions
Define in `app/<domain>/exceptions.py`. Inherit from `Exception`.

```python
class PlantNotFound(Exception): pass
class DeviceAlreadyRegistered(Exception): pass
```

### Exception → HTTP mapping (in route layer only)
```python
@router.get("/{plant_id}")
def get_plant(plant_id: int, service: PlantService = Depends(...)):
    try:
        return service.get_plant(plant_id)
    except PlantNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
```

### Rules
- Services raise domain exceptions; routes catch them and raise `HTTPException`
- Never raise `HTTPException` inside a service
- Never catch bare `Exception` in services unless wrapping into a domain exception

---

## Testing Conventions

### Structure
- `tests/test_<domain>_service.py` — unit tests calling the service directly
- `tests/test_<domain>_api.py` — integration tests via `TestClient`
- `tests/conftest.py` — shared fixtures (in-memory DB, `client`, `db`)

### Service unit tests
```python
def make_service(db) -> PlantService:
    return PlantService(db)  # no AI needed for non-AI tests

@pytest.mark.asyncio
async def test_raises_no_profile_image(db):
    svc = make_service(db)
    plant = svc.create_plant(name="Fern", device_id="DEV001")
    with pytest.raises(NoProfileImage):
        await svc.identify_species(plant.id)
```

### Mocking the AI provider (integration tests)
When testing routes that call the AI, patch at the `OpenAIProvider` class level:

```python
from unittest.mock import AsyncMock, patch

mock_ai = AsyncMock()
mock_ai.complete = AsyncMock(return_value='{"species":"Fern","confidence":"High","care_guide":{}}')

with patch("app.core.protocols.OpenAIProvider", return_value=mock_ai):
    response = client.post("/api/v1/plants/1/identify-species")
```

For service-level tests (no factory), patch `app.plant.service.AsyncOpenAI` directly (legacy path is preserved when `ai=None`).

### File system in tests
Always use `tempfile.TemporaryDirectory()` for tests that write files, and patch `settings.MEDIA_ROOT` to the temp dir:

```python
with tempfile.TemporaryDirectory() as tmpdir, \
     patch("app.plant.service.settings") as ms:
    ms.MEDIA_ROOT = tmpdir
    result = service.save_image(plant_id=1, file_bytes=b"...", filename="photo.jpg")
```

---

## API Versioning

All REST endpoints live under `/api/v1/`. UI (HTML) routes are unversioned.

```
REST API:  /api/v1/plants/       → app/api/v1/plants.py
REST API:  /api/v1/ingest        → app/api/v1/ingest.py
REST API:  /api/v1/health/       → app/api/v1/health.py
UI routes: /catalog, /catalog/:id → app/ui/routes.py
```

When a breaking API change is needed:
1. Create `app/api/v2/` with the new endpoints
2. Register `v2_router` in `app/api/router.py`
3. Keep v1 operational until all clients are migrated
4. Document the migration in a changelog

---

## Design Patterns in Use

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Factory** | `app/core/factory.py` | Central service construction; single place to wire dependencies |
| **Strategy** | `app/core/protocols.py` (`AIProviderProtocol`) | Swap AI provider without changing service code |
| **Decorator** | `app/core/logging.py` (`@log_call`) | Cross-cutting concern (logging) added without touching business logic |
| **Repository** | `app/*/repository.py` | Isolate DB queries; swap storage backends in tests |
| **Protocol** | `app/core/protocols.py` | Structural typing contracts without inheritance; enables easy mocking |

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `app/core/config.py` | App settings via `pydantic-settings` (env vars / `.env`) |
| `app/core/database.py` | SQLAlchemy engine + `get_db` FastAPI dependency |
| `app/core/factory.py` | `ServiceFactory` — construct all services here |
| `app/core/protocols.py` | `AIProviderProtocol`, `OpenAIProvider`, `RepositoryProtocol` |
| `app/core/logging.py` | `StructuredLogger`, `get_logger`, `log_call`, `configure_logging` |
| `app/api/deps.py` | FastAPI dependency functions — use `ServiceFactory` here |
| `app/api/v1/router.py` | Aggregates all v1 sub-routers |
| `app/lifespan.py` | App startup/shutdown (logging init, DB migrations) |
