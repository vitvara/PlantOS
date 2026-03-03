import base64
import json
import os
import uuid
from typing import List, Optional

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.health.exceptions import AnalysisError, TooManyImages
from app.health.models import PlantHealthLog
from app.health.repository import HealthLogRepository


settings = get_settings()

MAX_IMAGES = 3
_HEALTH_SUBDIR = "health"
_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_BASE_PROMPT = """You are a plant health expert. Analyze the provided plant image(s) carefully.{species_context}

Respond ONLY with valid JSON — no markdown, no extra text:
{{
  "health_score": <integer 0–100>,
  "summary": "<1–2 sentence overall assessment>",
  "issues": ["<observed problem>", ...],
  "suggestions": ["<actionable recommendation>", ...]
}}

Score guide: 90–100 excellent · 70–89 good · 50–69 fair · 30–49 poor · 0–29 critical.
Use empty lists [] when there are no issues or suggestions."""


def _build_prompt(species: str | None) -> str:
    if species and species != "Unknown":
        context = (
            f"\n\nThis plant has been identified as: {species}. "
            "Diagnose and treat it accordingly — apply species-specific knowledge about "
            "its ideal conditions, common diseases, and care requirements."
        )
    else:
        context = ""
    return _BASE_PROMPT.format(species_context=context)


class PlantHealthService:
    """
    Orchestrates GPT-4o vision analysis and persists results.
    """

    def __init__(self, db: Session):
        self.repo = HealthLogRepository(db)

    # ------------------------------------------------
    # Public API
    # ------------------------------------------------
    async def analyze(
        self,
        plant_id: int,
        images: List[bytes],
        filenames: List[str | None],
        species: str | None = None,
    ) -> PlantHealthLog:
        if not images:
            raise AnalysisError("At least one image is required")
        if len(images) > MAX_IMAGES:
            raise TooManyImages(f"Maximum {MAX_IMAGES} images per analysis")
        if not settings.OPENAI_API_KEY:
            raise AnalysisError("OPENAI_API_KEY is not configured")

        image_paths = self._save_images(images, filenames)
        result = await self._call_openai(images, filenames, species=species)

        return self.repo.create(
            plant_id=plant_id,
            image_paths=image_paths,
            health_score=result["health_score"],
            summary=result["summary"],
            issues=result["issues"],
            suggestions=result["suggestions"],
        )

    def get_history(self, plant_id: int) -> List[PlantHealthLog]:
        return self.repo.get_by_plant(plant_id)

    def get_latest(self, plant_id: int) -> Optional[PlantHealthLog]:
        return self.repo.get_latest_by_plant(plant_id)

    # ------------------------------------------------
    # Private helpers
    # ------------------------------------------------
    def _save_images(self, images: List[bytes], filenames: List[str | None]) -> List[str]:
        dest = os.path.join(settings.MEDIA_ROOT, _HEALTH_SUBDIR)
        os.makedirs(dest, exist_ok=True)

        paths: List[str] = []
        for raw, name in zip(images, filenames):
            ext = os.path.splitext(name or "")[1].lower() or ".jpg"
            rel = f"{_HEALTH_SUBDIR}/{uuid.uuid4().hex}{ext}"
            with open(os.path.join(settings.MEDIA_ROOT, rel), "wb") as fh:
                fh.write(raw)
            paths.append(rel)
        return paths

    async def _call_openai(
        self, images: List[bytes], filenames: List[str | None], species: str | None = None
    ) -> dict:
        content: list = [{"type": "text", "text": _build_prompt(species)}]

        for raw, name in zip(images, filenames):
            ext = os.path.splitext(name or "")[1].lower()
            mime = _MIME.get(ext, "image/jpeg")
            b64 = base64.b64encode(raw).decode()
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}",
                    "detail": "low",
                },
            })

        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": content}],
                max_tokens=600,
            )
            parsed = json.loads(response.choices[0].message.content)
            return {
                "health_score": max(0, min(100, int(parsed.get("health_score", 50)))),
                "summary": str(parsed.get("summary", "Analysis complete.")),
                "issues": [str(i) for i in (parsed.get("issues") or [])],
                "suggestions": [str(s) for s in (parsed.get("suggestions") or [])],
            }
        except AnalysisError:
            raise
        except Exception as exc:
            raise AnalysisError(f"OpenAI call failed: {exc}") from exc
