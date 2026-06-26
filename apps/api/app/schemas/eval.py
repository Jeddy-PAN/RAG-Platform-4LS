import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.eval import EvalRunStatus
from app.models.retrieval import RetrievalMode


class EvalDatasetCreate(BaseModel):
    """Request body for creating an eval dataset."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = None

    @model_validator(mode="after")
    def trim_fields(self) -> "EvalDatasetCreate":
        """Normalize dataset text fields."""

        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name must not be empty")
        if self.description is not None:
            self.description = self.description.strip() or None
        return self


class EvalDatasetRead(BaseModel):
    """Eval dataset summary returned by list and create endpoints."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    question_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvalQuestionCreate(BaseModel):
    """Request body for adding an eval question."""

    question: str = Field(min_length=1)
    expected_document_id: uuid.UUID | None = None
    expected_chunk_id: uuid.UUID | None = None
    expected_answer_notes: str | None = None
    should_answer: bool = True

    @model_validator(mode="after")
    def trim_question_fields(self) -> "EvalQuestionCreate":
        """Normalize question text fields."""

        self.question = self.question.strip()
        if not self.question:
            raise ValueError("question must not be empty")
        if self.expected_answer_notes is not None:
            self.expected_answer_notes = self.expected_answer_notes.strip() or None
        return self


class EvalQuestionRead(BaseModel):
    """Eval question returned by question endpoints."""

    id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    question: str
    expected_document_id: uuid.UUID | None
    expected_chunk_id: uuid.UUID | None
    expected_answer_notes: str | None
    should_answer: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvalRunCreate(BaseModel):
    """Request body for running an eval dataset."""

    retrieval_mode: RetrievalMode = RetrievalMode.hybrid
    top_k: int = Field(default=8, ge=1, le=50)
    vector_weight: float = Field(default=0.65, ge=0, le=1)
    keyword_weight: float = Field(default=0.35, ge=0, le=1)

    @model_validator(mode="after")
    def validate_weights(self) -> "EvalRunCreate":
        """Reject zero-total hybrid weights."""

        if (
            self.retrieval_mode == RetrievalMode.hybrid
            and self.vector_weight + self.keyword_weight <= 0
        ):
            raise ValueError("hybrid weights must not both be zero")
        return self


class EvalResultRead(BaseModel):
    """Per-question eval result."""

    id: uuid.UUID
    question_id: uuid.UUID
    question: str
    answer: str | None
    hit: bool
    citation_covered: bool
    refused: bool
    answer_matched: bool
    retrieval_latency_ms: int | None
    generation_latency_ms: int | None
    score: float | None
    result_metadata: dict


class EvalRunRead(BaseModel):
    """Eval run with aggregate metrics and per-question results."""

    id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    status: EvalRunStatus
    retrieval_mode: str
    top_k: int
    metrics: dict
    error_message: str | None
    results: list[EvalResultRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
