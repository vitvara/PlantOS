"""
Shared pytest fixtures for PlantOS tests.

Uses an in-memory SQLite database so tests are fast and isolated.
The `get_db` FastAPI dependency is overridden so every test gets
its own clean session that is rolled back after the test.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import Base, get_db
from app.main import create_application


# ---------------------------------------------------------------------------
# In-memory SQLite engine shared by all tests (tables created once)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base.metadata.create_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Per-test DB session (rolls back after each test)
# ---------------------------------------------------------------------------
@pytest.fixture()
def db() -> Session:
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# FastAPI TestClient with overridden DB dependency
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(db: Session) -> TestClient:
    app = create_application()

    def override_get_db():
        try:
            yield db
            db.flush()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
