import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class EvalRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class EvalDataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Project-scoped group of evaluation questions."""

    __tablename__ = "eval_datasets"
    __table_args__ = (Index("ix_eval_datasets_project", "project_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    questions: Mapped[list["EvalQuestion"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["EvalRun"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


class EvalQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Expected-answer test case used to measure retrieval and generation."""

    __tablename__ = "eval_questions"
    __table_args__ = (
        Index("ix_eval_questions_project_dataset", "project_id", "dataset_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    expected_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    expected_answer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    should_answer: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    dataset: Mapped[EvalDataset] = relationship(back_populates="questions")


class EvalRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Execution record for running one eval dataset with chosen settings."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_project_dataset", "project_id", "dataset_id"),
        Index("ix_eval_runs_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[EvalRunStatus] = mapped_column(
        Enum(EvalRunStatus, name="eval_run_status"),
        nullable=False,
        default=EvalRunStatus.queued,
    )
    retrieval_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset: Mapped[EvalDataset] = relationship(back_populates="runs")
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvalResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-question metrics captured during an evaluation run."""

    __tablename__ = "eval_results"
    __table_args__ = (Index("ix_eval_results_project_run", "project_id", "run_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    citation_covered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    refused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    run: Mapped[EvalRun] = relationship(back_populates="results")
