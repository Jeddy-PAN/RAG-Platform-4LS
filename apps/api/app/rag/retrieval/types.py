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
class TableQueryFacet:
    index: int
    query: str


@dataclass(frozen=True)
class TableQueryPlan:
    original_query: str
    facets: list[TableQueryFacet]
    is_compound: bool = False


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


@dataclass(frozen=True)
class FacetTableContextCoverage:
    facet_indexes: tuple[int, ...]
    selection: TableSelectionCandidate
    coverage: TableContextCoverage
    is_partial: bool = False

    def to_metadata(self) -> dict:
        return {
            "facet_indexes": list(self.facet_indexes),
            **self.coverage.to_metadata(),
            "is_partial": self.is_partial,
        }


@dataclass(frozen=True)
class TableFacetOutcome:
    facet: TableQueryFacet
    status: str
    selected: TableSelectionCandidate | None = None
    candidates: list[TableSelectionCandidate] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class TableSelectionPlan:
    original_query: str
    outcomes: list[TableFacetOutcome] = field(default_factory=list)

    @property
    def requires_clarification(self) -> bool:
        return any(outcome.status == "ambiguous" for outcome in self.outcomes)

    @property
    def selected_outcomes(self) -> list[TableFacetOutcome]:
        return [
            outcome
            for outcome in self.outcomes
            if outcome.status == "selected" and outcome.selected is not None
        ]

    @property
    def unresolved_facet_indexes(self) -> list[int]:
        return [
            outcome.facet.index
            for outcome in self.outcomes
            if outcome.status != "selected" or outcome.selected is None
        ]

    @property
    def can_generate(self) -> bool:
        return bool(self.outcomes) and not self.unresolved_facet_indexes

    def to_metadata(self) -> dict:
        def serialize_candidate(candidate: TableSelectionCandidate) -> dict:
            return {
                **candidate.identity_metadata(),
                "score": candidate.score,
                "score_breakdown": candidate.score_breakdown,
            }

        return {
            "original_query": self.original_query,
            "can_generate": self.can_generate,
            "requires_clarification": self.requires_clarification,
            "unresolved_facet_indexes": self.unresolved_facet_indexes,
            "facets": [
                {
                    "index": outcome.facet.index,
                    "query": outcome.facet.query,
                    "status": outcome.status,
                    "reason": outcome.reason,
                    "selected": (
                        serialize_candidate(outcome.selected)
                        if outcome.selected is not None
                        else None
                    ),
                    "candidates": [
                        serialize_candidate(candidate)
                        for candidate in outcome.candidates
                    ],
                }
                for outcome in self.outcomes
            ],
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
    table_selection_plan: TableSelectionPlan | None = None
    table_contexts: list[FacetTableContextCoverage] = field(default_factory=list)
