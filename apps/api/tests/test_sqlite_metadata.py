from sqlalchemy import create_engine

from app.db.base import Base
import app.models  # noqa: F401


def test_model_metadata_can_create_sqlite_test_schema() -> None:
    """ORM metadata should support fast local tests without PostgreSQL."""

    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    assert "projects" in Base.metadata.tables
