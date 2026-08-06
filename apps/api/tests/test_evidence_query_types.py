"""Contract tests for Round 4B generic evidence-facet types."""

import json
import uuid

import pytest

from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    EvidenceSelectionPlan,
    FacetEvidenceCoverage,
    QueryEntity,
)


def _single_plan(**overrides) -> EvidenceQueryPlan:
    values = dict(
        original_query="find the username for node-17",
        facets=(EvidenceFacet(index=0, query="username for node-17"),),
        route="deterministic",
        confidence=0.9,
    )
    values.update(overrides)
    return EvidenceQueryPlan(**values)


def _multi_plan() -> EvidenceQueryPlan:
    return EvidenceQueryPlan(
        original_query="find the username and password for node-17",
        facets=(
            EvidenceFacet(index=0, query="username for node-17"),
            EvidenceFacet(index=1, query="password for node-17"),
        ),
        route="deterministic",
        confidence=0.8,
    )


def test_valid_single_facet_plan() -> None:
    plan = _single_plan()
    assert len(plan.facets) == 1
    assert plan.to_metadata()["facet_count"] == 1
    assert plan.to_metadata()["facet_indexes"] == [0]


def test_valid_multi_facet_plan() -> None:
    plan = _multi_plan()
    assert [facet.index for facet in plan.facets] == [0, 1]


def test_non_contiguous_facet_indexes_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceQueryPlan(
            original_query="q",
            facets=(EvidenceFacet(index=0, query="a"), EvidenceFacet(index=2, query="b")),
            route="deterministic",
            confidence=0.8,
        )


def test_more_than_four_facets_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceQueryPlan(
            original_query="q",
            facets=tuple(EvidenceFacet(index=i, query=f"f{i}") for i in range(5)),
            route="deterministic",
            confidence=0.8,
        )


def test_empty_facet_plan_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceQueryPlan(
            original_query="q",
            facets=(),
            route="single",
            confidence=0.0,
        )


def test_illegal_route_rejected() -> None:
    with pytest.raises(ValueError):
        _single_plan(route="magic")


def test_illegal_coverage_status_rejected() -> None:
    plan = _single_plan()
    with pytest.raises(ValueError):
        FacetEvidenceCoverage(facet_index=0, status="maybe")


def test_duplicate_coverage_facet_rejected() -> None:
    plan = _multi_plan()
    with pytest.raises(ValueError):
        EvidenceSelectionPlan(
            query_plan=plan,
            coverage=(
                FacetEvidenceCoverage(facet_index=0, status="covered"),
                FacetEvidenceCoverage(facet_index=0, status="unresolved"),
            ),
        )


def test_coverage_reference_to_unknown_facet_rejected() -> None:
    plan = _single_plan()
    with pytest.raises(ValueError):
        EvidenceSelectionPlan(
            query_plan=plan,
            coverage=(FacetEvidenceCoverage(facet_index=7, status="covered"),),
        )


def test_confidence_bucket() -> None:
    assert _single_plan(confidence=0.9).confidence_bucket == "high"
    assert _multi_plan().confidence_bucket == "high"
    assert _single_plan(confidence=0.6).confidence_bucket == "medium"
    assert _single_plan(confidence=0.3).confidence_bucket == "low"


def test_metadata_is_redacted() -> None:
    """Persisted metadata must not contain raw queries, entities, or attributes."""

    secret_entity = "node-17"
    plan = EvidenceQueryPlan(
        original_query="find the username and password for node-17",
        facets=(
            EvidenceFacet(
                index=0,
                query="username for node-17",
                entities=(QueryEntity(text="node-17", normalized="node17"),),
                attributes=("username",),
            ),
            EvidenceFacet(
                index=1,
                query="password for node-17",
                entities=(QueryEntity(text="node-17", normalized="node17"),),
                attributes=("password",),
            ),
        ),
        route="structured",
        confidence=0.75,
    )
    selection = EvidenceSelectionPlan(
        query_plan=plan,
        coverage=(
            FacetEvidenceCoverage(
                facet_index=0,
                status="covered",
                selected_chunk_ids=(uuid.uuid4(),),
            ),
            FacetEvidenceCoverage(
                facet_index=1,
                status="unresolved",
                reason="budget_exhausted",
            ),
        ),
    )

    metadata = selection.to_metadata()
    serialized = json.dumps(metadata)
    assert "node-17" not in serialized
    assert "username" not in serialized
    assert "password" not in serialized
    assert "find the username" not in serialized
    assert "facet_count" in metadata
    assert metadata["facet_indexes"] == [0, 1]
    assert metadata["route"] == "structured"
    assert metadata["confidence_bucket"] == "medium"
    assert len(metadata["coverage"]) == 2
    assert metadata["coverage"][1]["reason"] == "budget_exhausted"
    assert metadata["coverage"][1]["status"] == "unresolved"


def test_metadata_serialization_is_stable() -> None:
    plan = _multi_plan()
    coverage = (
        FacetEvidenceCoverage(facet_index=0, status="covered"),
        FacetEvidenceCoverage(facet_index=1, status="unresolved"),
    )
    first = EvidenceSelectionPlan(query_plan=plan, coverage=coverage).to_metadata()
    second = EvidenceSelectionPlan(query_plan=plan, coverage=coverage).to_metadata()
    assert first == second
