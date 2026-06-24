from collections.abc import Iterator
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="session")
def isolated_database_url() -> Iterator[str]:
    """Create a disposable PostgreSQL database for integration tests."""

    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is required for database integration tests")

    source_url = make_url(raw_url)
    base_name = source_url.database or "rag"
    database_name = f"{base_name}_test_{uuid.uuid4().hex[:12]}"
    maintenance_database = "postgres" if base_name != "postgres" else "template1"
    maintenance_url = source_url.set(database=maintenance_database)
    test_url = source_url.set(database=database_name)

    admin_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except SQLAlchemyError as exc:
        admin_engine.dispose()
        pytest.skip(f"could not create isolated PostgreSQL test database: {exc}")

    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


@pytest.fixture()
def migrated_engine(isolated_database_url: str) -> Iterator[Engine]:
    """Apply Alembic migrations and yield an engine bound to the test DB."""

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)

    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def sqlite_session_factory():
    """Create an in-memory SQLite session factory for API tests."""

    from app.db.base import Base
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    finally:
        engine.dispose()


@pytest.fixture()
def api_client(sqlite_session_factory):
    """Create a FastAPI test client wired to an isolated SQLite database."""

    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    def override_get_db():
        db = sqlite_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
