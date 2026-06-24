from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine(database_url: str | None = None):
    """Create the PostgreSQL engine used by API requests and workers."""

    settings = get_settings()
    url = database_url or settings.database_url
    return create_engine(url, pool_pre_ping=True)


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield one database session for a FastAPI request dependency."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
