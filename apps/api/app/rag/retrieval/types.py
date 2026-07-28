from dataclasses import dataclass, field
import uuid


@dataclass
class RetrievalCandidate:
    """Internal retrieval candidate before API serialization."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    text: str
    source_metadata: dict
    vector_score: float | None = None
    keyword_score: float | None = None
    fused_score: float | None = None
    rank: int | None = None
    score_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TableSelectionCandidate:
    """One table identity considered during project-wide table selection."""

    document_id: uuid.UUID
    document_name: str
    table_index: int
    caption: str | None = None
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    def identity_metadata(self) -> dict:
        """Return stable identity fields suitable for message metadata."""

        return {
            "document_id": str(self.document_id),
            "document_name": self.document_name,
            "table_index": self.table_index,
            "caption": self.caption,
        }


@dataclass(frozen=True)
class TableSelectionOutcome:
    """Structured outcome passed from retrieval into chat orchestration."""

    status: str
    selected: TableSelectionCandidate | None = None
    candidates: list[TableSelectionCandidate] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class TableContextCoverage:
    """Rows from a selected table that are present in the model context."""

    document_id: uuid.UUID
    document_name: str
    table_index: int
    row_ranges: list[tuple[int, int]] = field(default_factory=list)
    total_rows: int | None = None

    def to_metadata(self) -> dict:
        """Serialize coverage for retrieval logs and assistant metadata."""

        return {
            "document_id": str(self.document_id),
            "document_name": self.document_name,
            "table_index": self.table_index,
            "row_ranges": [list(row_range) for row_range in self.row_ranges],
            "total_rows": self.total_rows,
        }


@dataclass
class RetrievalResult:
    """Complete retrieval response assembled by the service layer."""

    query: str
    mode: str
    top_k: int
    latency_ms: int
    results: list[RetrievalCandidate]
    retrieval_log_id: uuid.UUID
    table_selection: TableSelectionOutcome | None = None
    context_partial: bool = False
    table_context: TableContextCoverage | None = None
