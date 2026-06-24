import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class IngestionJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Uploaded source file tracked before and after ingestion."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_project_id_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        nullable=False,
        default=DocumentStatus.uploaded,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="documents")
    sections: Mapped[list["DocumentSection"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Optional parsed document section used before chunking."""

    __tablename__ = "document_sections"
    __table_args__ = (
        Index("ix_document_sections_project_document", "project_id", "document_id"),
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
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    document: Mapped[Document] = relationship(back_populates="sections")


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Queue-backed processing record for parsing and indexing one document."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_project_status", "project_id", "status"),
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
    status: Mapped[IngestionJobStatus] = mapped_column(
        Enum(IngestionJobStatus, name="ingestion_job_status"),
        nullable=False,
        default=IngestionJobStatus.queued,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    document: Mapped[Document] = relationship(back_populates="ingestion_jobs")
