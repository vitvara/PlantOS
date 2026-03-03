import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import List

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.plant.exceptions import (
    DeviceAlreadyRegistered,
    NoProfileImage,
    PlantNotFound,
    SpeciesIdentificationError,
    UnsupportedImageFormat,
)
from app.plant.models import Plant
from app.plant.repository import PlantRepository


settings = get_settings()

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
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
    Business logic layer for the plant domain.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = PlantRepository(db)

    # ------------------------------------------------
    # Auto Registration (called by ingestion pipeline)
    # ------------------------------------------------
    def get_or_create_by_device(self, device_id: str) -> Plant:
        plant = self.repo.get_by_device_id(device_id)
        if plant:
            return plant
        return self.repo.create(name=f"Plant-{device_id[-4:]}", device_id=device_id)

    # ------------------------------------------------
    # Manual Creation (admin / UI)
    # ------------------------------------------------
    def create_plant(self, name: str, device_id: str) -> Plant:
        if self.repo.get_by_device_id(device_id):
            raise DeviceAlreadyRegistered(f"Device '{device_id}' is already registered")
        return self.repo.create(name=name, device_id=device_id)

    # ------------------------------------------------
    # Delete
    # ------------------------------------------------
    def delete_plant(self, plant_id: int) -> None:
        from app.health.repository import HealthLogRepository

        plant = self.get_plant(plant_id)

        # Collect media files to remove after DB delete
        files_to_remove: list[str] = []
        if plant.image_path:
            files_to_remove.append(os.path.join(settings.MEDIA_ROOT, plant.image_path))

        health_repo = HealthLogRepository(self.db)
        for log in health_repo.get_by_plant(plant_id):
            for img_path in (log.image_paths or []):
                files_to_remove.append(os.path.join(settings.MEDIA_ROOT, img_path))

        # Delete from DB (cascade removes health logs)
        self.repo.delete(plant)

        # Clean up files silently
        for path in files_to_remove:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------
    # Catalog
    # ------------------------------------------------
    def list_plants(self) -> List[Plant]:
        return self.repo.list_all()

    def get_plant(self, plant_id: int) -> Plant:
        plant = self.repo.get_by_id(plant_id)
        if not plant:
            raise PlantNotFound(f"Plant {plant_id} not found")
        return plant

    # ------------------------------------------------
    # Image Upload
    # ------------------------------------------------
    def save_image(self, plant_id: int, file_bytes: bytes, filename: str | None) -> Plant:
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

    # ------------------------------------------------
    # Species Identification
    # ------------------------------------------------
    async def identify_species(self, plant_id: int) -> Plant:
        plant = self.get_plant(plant_id)

        if not plant.image_path:
            raise NoProfileImage("Plant has no profile image — upload a photo first")

        if not settings.OPENAI_API_KEY:
            raise SpeciesIdentificationError("OPENAI_API_KEY is not configured")

        image_path = os.path.join(settings.MEDIA_ROOT, plant.image_path)
        with open(image_path, "rb") as fh:
            raw = fh.read()

        ext = os.path.splitext(plant.image_path)[1].lower()
        mime = _MIME.get(ext, "image/jpeg")
        b64 = base64.b64encode(raw).decode()

        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4.1",
                response_format={"type": "json_object"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _SPECIES_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }],
                max_tokens=800,
            )
            parsed = json.loads(response.choices[0].message.content)
        except Exception as exc:
            raise SpeciesIdentificationError(f"OpenAI call failed: {exc}") from exc

        species = str(parsed.get("species", "Unknown"))
        species_thai = parsed.get("species_thai") or None
        confidence = parsed.get("confidence") or None
        care_guide = parsed.get("care_guide") or {}

        return self.repo.update_species(
            plant,
            species=species,
            care_guide=care_guide,
            identified_at=datetime.now(timezone.utc),
            species_thai=species_thai,
            confidence=confidence,
        )
