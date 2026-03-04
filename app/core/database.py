from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.engine import Engine

from app.core.config import get_settings


settings = get_settings()


# -------------------------
# Base Model (SQLAlchemy 2.0)
# -------------------------
class Base(DeclarativeBase):
    pass


# -------------------------
# Engine
# -------------------------
def create_db_engine() -> Engine:
    """
    Create database engine.
    Automatically configures SQLite correctly
    while remaining production-ready for Postgres.
    """
    if settings.database_url.startswith("sqlite"):
        eng = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            future=True,
            pool_pre_ping=True,
        )

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return eng

    # For Postgres / MySQL later
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
    )


engine: Engine = create_db_engine()


# -------------------------
# Session Factory
# -------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


# -------------------------
# Dependency (FastAPI)
# -------------------------
def get_db():
    """
    DB session dependency.
    Handles commit/rollback automatically.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()