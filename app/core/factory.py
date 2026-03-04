"""
ServiceFactory — centralised construction of all domain services.

Why a factory?
--------------
* **Single place for wiring**: adding a new dependency (cache, second AI
  model, feature flag client) only touches this file.
* **Testability**: tests can call ``ServiceFactory.plant_service(db, ai=mock)``
  to inject fakes without patching at the module level.
* **Decoupling**: callers (``app/api/deps.py``, tests) never ``import``
  concrete service constructors directly — only this factory.

Design pattern
--------------
*Factory* with class methods.  Class methods (rather than instance methods)
are used because the factory itself is stateless — it is never instantiated.

All service models are imported *inside* each class method to avoid circular
imports at module load time.

Example — in tests::

    from unittest.mock import AsyncMock
    from app.core.factory import ServiceFactory

    def test_identify_species(db):
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value='{"species":"Fern","confidence":"High","care_guide":{}}')
        svc = ServiceFactory.plant_service(db, ai=mock_ai)
        ...

Example — in FastAPI deps::

    def get_plant_service(db: Session = Depends(get_db)) -> PlantService:
        return ServiceFactory.plant_service(db)
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.protocols import AIProviderProtocol


class ServiceFactory:
    """
    Stateless factory that constructs domain service instances.

    All methods are class methods — this class is never instantiated.

    The *ai* parameter on services that require an AI provider is optional:
    when omitted the service falls back to its internal OpenAI client
    (backward-compatible with older tests).  Production code always passes
    an :class:`~app.core.protocols.OpenAIProvider` instance.
    """

    # ------------------------------------------------------------------
    # Plant domain
    # ------------------------------------------------------------------

    @classmethod
    def plant_service(
        cls,
        db: Session,
        ai: Optional[AIProviderProtocol] = None,
    ):
        """
        Create a :class:`~app.plant.service.PlantService`.

        Args:
            db: Active SQLAlchemy session (injected by FastAPI).
            ai: AI provider for species identification.  When ``None`` the
                service creates its own ``AsyncOpenAI`` client using
                ``settings.OPENAI_API_KEY`` (legacy behaviour preserved for
                backward compatibility).

        Returns:
            A fully wired :class:`~app.plant.service.PlantService` instance.
        """
        from app.plant.service import PlantService

        if ai is None:
            from app.core.config import get_settings
            from app.core.protocols import OpenAIProvider
            s = get_settings()
            if s.OPENAI_API_KEY:
                ai = OpenAIProvider(api_key=s.OPENAI_API_KEY, model="gpt-4.1")

        return PlantService(db=db, ai=ai)

    # ------------------------------------------------------------------
    # Health domain
    # ------------------------------------------------------------------

    @classmethod
    def health_service(
        cls,
        db: Session,
        ai: Optional[AIProviderProtocol] = None,
    ):
        """
        Create a :class:`~app.health.service.PlantHealthService`.

        Args:
            db: Active SQLAlchemy session.
            ai: AI provider for image-based health analysis.  Falls back to
                an inline ``AsyncOpenAI`` client when ``None``.

        Returns:
            A fully wired :class:`~app.health.service.PlantHealthService`.
        """
        from app.health.service import PlantHealthService

        if ai is None:
            from app.core.config import get_settings
            from app.core.protocols import OpenAIProvider
            s = get_settings()
            if s.OPENAI_API_KEY:
                ai = OpenAIProvider(api_key=s.OPENAI_API_KEY, model="gpt-4o")

        return PlantHealthService(db=db, ai=ai)

    # ------------------------------------------------------------------
    # Ingestion domain
    # ------------------------------------------------------------------

    @classmethod
    def ingestion_service(cls, db: Session):
        """
        Create an :class:`~app.ingestion.service.IngestionService`.

        Args:
            db: Active SQLAlchemy session.

        Returns:
            A fully wired :class:`~app.ingestion.service.IngestionService`.
        """
        from app.ingestion.service import IngestionService
        return IngestionService(db=db)

    # ------------------------------------------------------------------
    # UI / Dashboard
    # ------------------------------------------------------------------

    @classmethod
    def dashboard_service(cls, db: Session):
        """
        Create a :class:`~app.ui.service.DashboardService`.

        Args:
            db: Active SQLAlchemy session.

        Returns:
            A fully wired :class:`~app.ui.service.DashboardService`.
        """
        from app.ui.service import DashboardService
        return DashboardService(db=db)
