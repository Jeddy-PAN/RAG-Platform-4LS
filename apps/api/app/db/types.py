from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR


def uuid_type() -> Uuid:
    """Return a UUID type that works on PostgreSQL and SQLite tests."""

    return Uuid(as_uuid=True)


def json_dict_type():
    """Return JSONB in PostgreSQL and JSON in SQLite tests."""

    return JSONB().with_variant(JSON(), "sqlite")


def search_vector_type():
    """Return PostgreSQL tsvector with a text fallback for SQLite tests."""

    return TSVECTOR().with_variant(Text(), "sqlite")


def embedding_vector_type(dimensions: int):
    """Return pgvector with a JSON fallback for SQLite tests."""

    return Vector(dimensions).with_variant(JSON(), "sqlite")
