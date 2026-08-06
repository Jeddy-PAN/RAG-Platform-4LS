"""Generic entity/attribute evidence-facet types for Round 4B.

These types are deliberately separate from the Round 4A table plan types:
fact coverage and table expansion have different status and budget semantics.
All serializers here are redacted: raw facet queries, entity text, attributes,
source/search text, and extracted fact values are never included in persisted
metadata.
"""

import uuid
from dataclasses import dataclass

MAX_EVIDENCE_FACETS = 4
COVERAGE_STATUSES = ("covered", "unresolved", "conflicting")
PLANNER_ROUTES = ("single", "deterministic", "structured", "fallback")


@dataclass(frozen=True)
class QueryEntity:
    """A question-grounded entity span."""

    text: str
    normalized: str


@dataclass(frozen=True)
class EvidenceFacet:
    """One independent requested fact, grounded in the original question."""

    index: int
    query: str
    entities: tuple[QueryEntity, ...] = ()
    attributes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceQueryPlan:
    """Conservative generic plan with stable, zero-based facet indexes."""

    original_query: str
    facets: tuple[EvidenceFacet, ...]
    route: str
    confidence: float
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        if self.route not in PLANNER_ROUTES:
            raise ValueError(f"illegal planner route: {self.route}")
        if not 1 <= len(self.facets) <= MAX_EVIDENCE_FACETS:
            raise ValueError("facet count must be between 1 and 4")
        indexes = [facet.index for facet in self.facets]
        if indexes != list(range(len(self.facets))):
            raise ValueError("facet indexes must be contiguous starting at 0")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    @property
    def confidence_bucket(self) -> str:
        if self.confidence >= 0.8:
            return "high"
        if self.confidence >= 0.5:
            return "medium"
        return "low"

    def to_metadata(self) -> dict:
        """Redacted metadata: no facet queries, entities, or attributes."""

        return {
            "route": self.route,
            "confidence_bucket": self.confidence_bucket,
            "fallback_reason": self.fallback_reason,
            "facet_count": len(self.facets),
            "facet_indexes": [facet.index for facet in self.facets],
        }


@dataclass(frozen=True)
class FacetEvidenceCoverage:
    """Terminal coverage state for one planned facet."""

    facet_index: int
    status: str
    selected_chunk_ids: tuple[uuid.UUID, ...] = ()
    conflict_groups: tuple[tuple[uuid.UUID, ...], ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in COVERAGE_STATUSES:
            raise ValueError(f"illegal coverage status: {self.status}")

    def to_metadata(self) -> dict:
        """Redacted metadata: chunk IDs and reason codes only."""

        return {
            "facet_index": self.facet_index,
            "status": self.status,
            "reason": self.reason,
            "selected_chunk_ids": [str(chunk_id) for chunk_id in self.selected_chunk_ids],
            "conflict_groups": [
                [str(chunk_id) for chunk_id in group]
                for group in self.conflict_groups
            ],
        }


@dataclass(frozen=True)
class FacetAssessment:
    """Strict assessor output: supporting chunk IDs and distinct claim groups.

    Never contains extracted values; groups reference chunk IDs only.
    """

    facet_index: int
    supporting_chunk_ids: tuple[uuid.UUID, ...] = ()
    conflict_groups: tuple[tuple[uuid.UUID, ...], ...] = ()


@dataclass(frozen=True)
class EvidenceSelectionPlan:
    """Query plan plus explicit terminal coverage for every facet."""

    query_plan: EvidenceQueryPlan
    coverage: tuple[FacetEvidenceCoverage, ...]

    def __post_init__(self) -> None:
        plan_indexes = {facet.index for facet in self.query_plan.facets}
        coverage_indexes = [coverage.facet_index for coverage in self.coverage]
        if len(coverage_indexes) != len(set(coverage_indexes)):
            raise ValueError("duplicate coverage facet indexes")
        if set(coverage_indexes) != plan_indexes:
            raise ValueError("coverage must contain exactly one state per facet")
        for coverage in self.coverage:
            if coverage.facet_index not in plan_indexes:
                raise ValueError("coverage references an unknown facet")

    def to_metadata(self) -> dict:
        return {
            **self.query_plan.to_metadata(),
            "coverage": [coverage.to_metadata() for coverage in self.coverage],
        }
