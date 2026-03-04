from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine, Base
from app.core.logging import configure_logging


def _run_sqlite_migrations() -> None:
    """Add new columns to existing SQLite databases that predate them."""
    new_columns = [
        ("species_thai", "TEXT"),
        ("confidence",   "VARCHAR(10)"),
    ]
    with engine.connect() as conn:
        for col, col_type in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE plants ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass  # column already exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle handler.

    Responsibilities:
    - Configure structured JSON logging
    - Initialize database schema
    - Run lightweight SQLite migrations
    - Prepare external resources
    - Cleanup on shutdown
    """

    # -------------------------
    # Startup
    # -------------------------
    from app.core.config import get_settings
    settings = get_settings()
    configure_logging(debug=getattr(settings, "debug", False))

    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations()

    # Future:
    # - Connect to Redis
    # - Initialize MQTT client
    # - Warm caches
    # - Register metrics

    yield

    # -------------------------
    # Shutdown
    # -------------------------
    # Future:
    # - Close external connections
    # - Flush metrics
    pass
