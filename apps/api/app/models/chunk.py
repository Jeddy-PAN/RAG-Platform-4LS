import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Chunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Smallest retrievable text unit with vector and keyword search fields."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_project_document", "project_id", "document_id"),
        Index("ix_chunks_project_chunk_index", "project_id", "chunk_index"),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="chunks")
