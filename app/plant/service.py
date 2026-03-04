"""
Business-logic layer for the plant domain.

Responsibilities
----------------
* Plant registration (manual and auto-registration from device ingestion).
* Profile image upload and validation.
* Species identification via AI provider (OpenAI GPT-4.1 vision by default).
* Plant deletion including associated media cleanup.

Not responsible for
-------------------
* HTTP concerns — see ``app/api/v1/plants.py`` and ``app/ui/routes.py``.
* Direct database queries — delegated to :class:`~app.plant.repository.PlantRepository`.
* Constructing the AI client — injected via :class:`~app.core.factory.ServiceFactory`.

Typical usage
-------------
::

    # Via dependency injection (production)
    from app.core.factory import ServiceFactory
    svc = ServiceFactory.plant_service(db)
    plant = await svc.identify_species(plant_id=1)

    # Direct construction (tests)
    svc = PlantService(db=session, ai=mock_ai)
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, log_call
from app.core.protocols import AIProviderProtocol
from app.plant.exceptions import (
    DeviceAlreadyRegistered,
    NoProfileImage,
    PlantNotFound,
    SpeciesIdentificationError,
    UnsupportedImageFormat,
)
from app.plant.models import Plant
from app.plant.repository import PlantRepository

logger = get_logger(__name__)
settings = get_settings()

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_MIME: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
}
_SPECIES_PROMPT = """You are a botanist. Identify the plant species from the photo.

You MUST respond ONLY with valid JSON — no markdown, no extra text:
{
  "species": "<common name + scientific name, e.g. 'Peace Lily (Spathiphyllum wallisii)'>",
  "species_thai": "<Thai common name for this plant, e.g. 'สแปทิฟิลลัม'>",
  "confidence": "<High|Medium|Low>",
  "care_guide": {
    "Watering": "<frequency and amount>",
    "Light": "<light requirements>",
    "Soil": "<soil type>",
    "Temperature": "<ideal range>",
    "Humidity": "<humidity preference>",
    "Fertilizing": "<schedule and type>",
    "Common Issues": "<typical problems and solutions>"
  }
}
"""


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
        ai: Optional AI provider for species identification.  When ``None``
            the service falls back to creating its own ``AsyncOpenAI`` client
            (backward-compatible path used by legacy tests).  Production code
            always receives a provider from :class:`~app.core.factory.ServiceFactory`.
    """

    def __init__(self, db: Session, ai: Optional[AIProviderProtocol] = None) -> None:
        self.db   = db
        self.repo = PlantRepository(db)
        self._ai  = ai

    # ------------------------------------------------------------------ #
    # Auto-registration (called by ingestion pipeline)                     #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    def get_or_create_by_device(self, device_id: str) -> Plant:
        """
        Return an existing plant for *device_id* or create a new one.

        Used by the ingestion pipeline to auto-register unknown devices.

        Args:
            device_id: Unique hardware identifier (e.g. ``"ESP32_A1B2"``).

        Returns:
            Existing or newly created :class:`~app.plant.models.Plant`.
        """
        plant = self.repo.get_by_device_id(device_id)
        if plant:
            return plant
        return self.repo.create(name=f"Plant-{device_id[-4:]}", device_id=device_id)

    # ------------------------------------------------------------------ #
    # Manual creation (admin / UI)                                         #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    def create_plant(self, name: str, device_id: str) -> Plant:
        """
        Register a new plant manually.

        Args:
            name:      Human-readable plant name.
            device_id: Unique hardware device identifier.

        Returns:
            Newly created :class:`~app.plant.models.Plant`.

        Raises:
            DeviceAlreadyRegistered: If *device_id* is already registered.
        """
        if self.repo.get_by_device_id(device_id):
            raise DeviceAlreadyRegistered(f"Device '{device_id}' is already registered")
        return self.repo.create(name=name, device_id=device_id)

    # ------------------------------------------------------------------ #
    # Delete                                                               #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    def delete_plant(self, plant_id: int) -> None:
        """
        Delete a plant and all associated media files.

        Removes the plant record, all associated health logs, and every
        uploaded image from disk.  Filesystem errors are silently ignored
        so that a missing file does not block the database delete.

        Args:
            plant_id: Database ID of the plant to delete.

        Raises:
            PlantNotFound: If no plant with *plant_id* exists.
        """
        from app.health.repository import HealthLogRepository

        plant = self.get_plant(plant_id)

        files_to_remove: list[str] = []
        if plant.image_path:
            files_to_remove.append(os.path.join(settings.MEDIA_ROOT, plant.image_path))

        health_repo = HealthLogRepository(self.db)
        for log in health_repo.get_by_plant(plant_id):
            for img_path in (log.image_paths or []):
                files_to_remove.append(os.path.join(settings.MEDIA_ROOT, img_path))

        health_repo.delete_all_by_plant(plant_id)
        self.repo.delete(plant)

        for path in files_to_remove:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------ #
    # Catalog                                                              #
    # ------------------------------------------------------------------ #

    def list_plants(self) -> List[Plant]:
        """
        Return all registered plants ordered newest-first.

        Returns:
            List of :class:`~app.plant.models.Plant` instances.
        """
        return self.repo.list_all()

    def get_plant(self, plant_id: int) -> Plant:
        """
        Fetch a single plant by its primary key.

        Args:
            plant_id: Database ID of the plant.

        Returns:
            The matching :class:`~app.plant.models.Plant`.

        Raises:
            PlantNotFound: If no plant with *plant_id* exists.
        """
        plant = self.repo.get_by_id(plant_id)
        if not plant:
            raise PlantNotFound(f"Plant {plant_id} not found")
        return plant

    # ------------------------------------------------------------------ #
    # Image upload                                                         #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    def save_image(self, plant_id: int, file_bytes: bytes, filename: str | None) -> Plant:
        """
        Validate and persist a profile photo for a plant.

        Args:
            plant_id:   Database ID of the target plant.
            file_bytes: Raw image bytes from the upload.
            filename:   Original filename (used to derive the file extension).

        Returns:
            Updated :class:`~app.plant.models.Plant` with ``image_path`` set.

        Raises:
            PlantNotFound:          If *plant_id* does not exist.
            UnsupportedImageFormat: If the extension is not in the allow-list.
        """
        plant = self.get_plant(plant_id)

        if not filename:
            raise UnsupportedImageFormat("Upload must include a filename")

        ext = os.path.splitext(filename)[1].lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise UnsupportedImageFormat(f"Extension '{ext}' is not supported")

        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(settings.MEDIA_ROOT, unique_name)

        with open(path, "wb") as f:
            f.write(file_bytes)

        return self.repo.update_image(plant, image_path=unique_name)

    # ------------------------------------------------------------------ #
    # Species identification                                               #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    async def identify_species(self, plant_id: int) -> Plant:
        """
        Identify plant species from its profile photo using AI.

        Reads the plant's profile image from disk, encodes it as base64,
        and sends it to the configured AI provider.  The JSON response is
        parsed and persisted on the plant record.

        When an :class:`~app.core.protocols.AIProviderProtocol` was injected
        at construction time (production path via
        :class:`~app.core.factory.ServiceFactory`), it is used directly.
        Otherwise, an ``AsyncOpenAI`` client is created inline using
        ``settings.OPENAI_API_KEY`` (legacy / test path).

        Args:
            plant_id: Database ID of the plant to identify.

        Returns:
            Updated :class:`~app.plant.models.Plant` with ``species``,
            ``species_thai``, ``confidence``, ``care_guide``, and
            ``species_identified_at`` populated.

        Raises:
            PlantNotFound:             If *plant_id* does not exist.
            NoProfileImage:            If the plant has no uploaded photo.
            SpeciesIdentificationError: If the AI call fails or returns
                                        unparseable JSON.
        """
        plant = self.get_plant(plant_id)

        if not plant.image_path:
            raise NoProfileImage("Plant has no profile image — upload a photo first")

        if self._ai is None and not settings.OPENAI_API_KEY:
            raise SpeciesIdentificationError("OPENAI_API_KEY is not configured")

        image_path = os.path.join(settings.MEDIA_ROOT, plant.image_path)
        with open(image_path, "rb") as fh:
            raw = fh.read()

        ext  = os.path.splitext(plant.image_path)[1].lower()
        mime = _MIME.get(ext, "image/jpeg")
        b64  = base64.b64encode(raw).decode()

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": _SPECIES_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {
                        "url":    f"data:{mime};base64,{b64}",
                        "detail": "high",
                    },
                },
            ],
        }]

        try:
            if self._ai is not None:
                # Injected provider path (production via ServiceFactory)
                raw_text = await self._ai.complete(
                    messages,
                    response_format={"type": "json_object"},
                    max_tokens=800,
                )
            else:
                # Inline client path (backward-compatible for legacy tests)
                if not settings.OPENAI_API_KEY:
                    raise SpeciesIdentificationError("OPENAI_API_KEY is not configured")
                client   = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                response = await client.chat.completions.create(
                    model="gpt-4.1",
                    response_format={"type": "json_object"},
                    messages=messages,
                    max_tokens=800,
                )
                raw_text = response.choices[0].message.content

            parsed = json.loads(raw_text)

        except SpeciesIdentificationError:
            raise
        except Exception as exc:
            raise SpeciesIdentificationError(f"OpenAI call failed: {exc}") from exc

        return self.repo.update_species(
            plant,
            species=str(parsed.get("species", "Unknown")),
            species_thai=parsed.get("species_thai") or None,
            confidence=parsed.get("confidence") or None,
            care_guide=parsed.get("care_guide") or {},
            identified_at=datetime.now(timezone.utc),
        )
