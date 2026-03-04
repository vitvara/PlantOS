"""
Business-logic layer for the plant health domain.

Responsibilities
----------------
* Analyzing plant health from uploaded images via AI provider (GPT-4o vision).
* Saving health log images to disk.
* Querying health log history.

Not responsible for
-------------------
* HTTP concerns — see ``app/api/v1/health.py`` and ``app/ui/routes.py``.
* Direct database queries — delegated to :class:`~app.health.repository.HealthLogRepository`.
* Constructing the AI client — injected via :class:`~app.core.factory.ServiceFactory`.

Typical usage
-------------
::

    # Via dependency injection (production)
    from app.core.factory import ServiceFactory
    svc = ServiceFactory.health_service(db)
    log = await svc.analyze(plant_id=1, images=[img_bytes], filenames=["photo.jpg"])

    # Direct construction (tests)
    svc = PlantHealthService(db=session, ai=mock_ai)
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import List, Optional

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, log_call
from app.core.protocols import AIProviderProtocol
from app.health.exceptions import AnalysisError, TooManyImages
from app.health.models import PlantHealthLog
from app.health.repository import HealthLogRepository


logger = get_logger(__name__)
settings = get_settings()

MAX_IMAGES = 3
_HEALTH_SUBDIR = "health"
_MIME: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
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
    Orchestrates plant health analysis using AI vision.

    Responsibilities:
        - Validate and save uploaded health images to disk
        - Call AI provider with images for health analysis
        - Persist health log results via HealthLogRepository

    Not responsible for:
        - HTTP concerns (use routes layer)
        - Direct DB queries (use HealthLogRepository)

    Args:
        db: SQLAlchemy Session injected by FastAPI dependency.
        ai: Optional AI provider for health analysis.  When ``None``
            the service falls back to creating its own ``AsyncOpenAI`` client
            (backward-compatible path used by legacy tests).  Production code
            always receives a provider from :class:`~app.core.factory.ServiceFactory`.
    """

    def __init__(self, db: Session, ai: Optional[AIProviderProtocol] = None) -> None:
        self.repo = HealthLogRepository(db)
        self._ai  = ai

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @log_call(logger)
    async def analyze(
        self,
        plant_id: int,
        images: List[bytes],
        filenames: List[str | None],
        species: str | None = None,
    ) -> PlantHealthLog:
        """
        Analyze plant health from uploaded images using AI.

        Validates the image count, saves images to disk, calls the AI
        provider, and persists the structured result as a health log entry.

        Args:
            plant_id:  Database ID of the plant being analyzed.
            images:    List of raw image bytes (1–3 items).
            filenames: Original filenames matching *images* (used for extension).
            species:   Known species name for context-aware diagnosis (optional).

        Returns:
            Newly created :class:`~app.health.models.PlantHealthLog`.

        Raises:
            AnalysisError:  If AI call fails or images list is empty.
            TooManyImages:  If more than :data:`MAX_IMAGES` images are supplied.
        """
        if not images:
            raise AnalysisError("At least one image is required")
        if len(images) > MAX_IMAGES:
            raise TooManyImages(f"Maximum {MAX_IMAGES} images per analysis")
        if self._ai is None and not settings.OPENAI_API_KEY:
            raise AnalysisError("OPENAI_API_KEY is not configured")

        image_paths = self._save_images(images, filenames)
        result      = await self._call_ai(images, filenames, species=species)

        return self.repo.create(
            plant_id=plant_id,
            image_paths=image_paths,
            health_score=result["health_score"],
            summary=result["summary"],
            issues=result["issues"],
            suggestions=result["suggestions"],
        )

    def get_history(self, plant_id: int) -> List[PlantHealthLog]:
        """
        Return all health logs for a plant, newest first.

        Args:
            plant_id: Database ID of the plant.

        Returns:
            List of :class:`~app.health.models.PlantHealthLog` instances.
        """
        return self.repo.get_by_plant(plant_id)

    def get_latest(self, plant_id: int) -> Optional[PlantHealthLog]:
        """
        Return the most recent health log for a plant.

        Args:
            plant_id: Database ID of the plant.

        Returns:
            Most recent :class:`~app.health.models.PlantHealthLog`, or ``None``.
        """
        return self.repo.get_latest_by_plant(plant_id)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

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

    async def _call_ai(
        self,
        images: List[bytes],
        filenames: List[str | None],
        species: str | None = None,
    ) -> dict:
        content: list = [{"type": "text", "text": _build_prompt(species)}]

        for raw, name in zip(images, filenames):
            ext  = os.path.splitext(name or "")[1].lower()
            mime = _MIME.get(ext, "image/jpeg")
            b64  = base64.b64encode(raw).decode()
            content.append({
                "type": "image_url",
                "image_url": {
                    "url":    f"data:{mime};base64,{b64}",
                    "detail": "low",
                },
            })

        messages = [{"role": "user", "content": content}]

        try:
            if self._ai is not None:
                # Injected provider path (production via ServiceFactory)
                raw_text = await self._ai.complete(
                    messages,
                    response_format={"type": "json_object"},
                    max_tokens=600,
                )
            else:
                # Inline client path (backward-compatible for legacy tests)
                if not settings.OPENAI_API_KEY:
                    raise AnalysisError("OPENAI_API_KEY is not configured")
                client   = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                response = await client.chat.completions.create(
                    model="gpt-4o",
                    response_format={"type": "json_object"},
                    messages=messages,
                    max_tokens=600,
                )
                raw_text = response.choices[0].message.content

            parsed = json.loads(raw_text)
            return {
                "health_score": max(0, min(100, int(parsed.get("health_score", 50)))),
                "summary":      str(parsed.get("summary", "Analysis complete.")),
                "issues":       [str(i) for i in (parsed.get("issues") or [])],
                "suggestions":  [str(s) for s in (parsed.get("suggestions") or [])],
            }
        except AnalysisError:
            raise
        except Exception as exc:
            raise AnalysisError(f"OpenAI call failed: {exc}") from exc
