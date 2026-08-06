import uuid

from app.rag.retrieval.evidence_selection import select_evidence
from app.rag.retrieval.types import RetrievalCandidate


def _candidate(
    name: str,
    *,
    document_id: uuid.UUID | None = None,
    fused_score: float,
    score_metadata: dict | None = None,
    source_metadata: dict | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        document_name=f"{name}.txt",
        chunk_index=0,
        text=name,
        source_metadata=source_metadata or {},
        fused_score=fused_score,
        score_metadata=score_metadata or {},
    )


def test_strong_lexical_evidence_from_two_documents_survives_top_k() -> None:
    document_a = uuid.uuid4()
    document_b = uuid.uuid4()
    candidates = [
        _candidate(f"vector-{index}", document_id=document_a, fused_score=1.0 - index / 10)
        for index in range(4)
    ]
    exact = _candidate(
        "exact",
        document_id=document_a,
        fused_score=0.5,
        score_metadata={"keyword_exact_identifiers": 1},
    )
    containment = _candidate(
        "containment",
        document_id=document_b,
        fused_score=0.4,
        score_metadata={"keyword_contained_identifiers": 1},
    )

    results = select_evidence(candidates + [exact, containment], top_k=3)

    assert exact in results
    assert containment in results
    assert [candidate.rank for candidate in results] == [1, 2, 3]
    assert exact.score_metadata["evidence_selection_reason"] == "protected_exact_identifier"
    assert containment.score_metadata["evidence_selection_reason"] == (
        "protected_contained_identifier"
    )


def test_general_term_evidence_does_not_receive_a_protected_slot() -> None:
    document_id = uuid.uuid4()
    ranked = _candidate("ranked", document_id=document_id, fused_score=1.0)
    general = _candidate(
        "general",
        document_id=uuid.uuid4(),
        fused_score=0.1,
        score_metadata={
            "keyword_exact_ascii_terms": 8,
            "keyword_exact_cjk_terms": 4,
            "keyword_ngram_matches": 3,
        },
    )

    results = select_evidence([ranked, general], top_k=1)

    assert results == [ranked]
    assert results[0].score_metadata["evidence_selection_reason"] == "ranked_fill"


def test_keyword_only_raw_metadata_receives_the_same_protection() -> None:
    ranked = _candidate("ranked", document_id=uuid.uuid4(), fused_score=1.0)
    containment = _candidate(
        "raw-containment",
        document_id=uuid.uuid4(),
        fused_score=0.1,
        score_metadata={"contained_identifiers": 1},
    )

    results = select_evidence([ranked, containment], top_k=1)

    assert results == [containment]
    assert results[0].score_metadata["evidence_selection_reason"] == (
        "protected_contained_identifier"
    )


def test_direct_keyword_metadata_is_not_hidden_by_zero_namespaced_value() -> None:
    ranked = _candidate("ranked", document_id=uuid.uuid4(), fused_score=1.0)
    exact = _candidate(
        "raw-exact",
        document_id=uuid.uuid4(),
        fused_score=0.1,
        score_metadata={"keyword_exact_identifiers": 0, "exact_identifiers": 1},
    )

    results = select_evidence([ranked, exact], top_k=1)

    assert results == [exact]


def test_structural_parent_row_overlap_uses_one_slot_but_distinct_rows_survive() -> None:
    document_id = uuid.uuid4()
    common = {"table_index": 2}
    parent = _candidate(
        "parent",
        document_id=document_id,
        fused_score=0.9,
        source_metadata={
            **common,
            "table_chunk_type": "table_group",
            "data_row_start": 1,
            "data_row_end": 1,
        },
    )
    distinct_row = _candidate(
        "distinct-row",
        document_id=document_id,
        fused_score=0.8,
        source_metadata={**common, "table_chunk_type": "table_row", "data_row": 2},
    )
    exact_row = _candidate(
        "exact-row",
        document_id=document_id,
        fused_score=0.7,
        score_metadata={"keyword_exact_identifiers": 1},
        source_metadata={**common, "table_chunk_type": "table_row", "data_row": 1},
    )

    results = select_evidence([parent, distinct_row, exact_row], top_k=3)

    assert parent not in results
    assert {candidate.chunk_id for candidate in results} == {
        distinct_row.chunk_id,
        exact_row.chunk_id,
    }
    assert [candidate.rank for candidate in results] == [1, 2]


# ── Round 4B facet-aware evidence coverage ─────────────────────────

from app.rag.retrieval.evidence_selection import select_evidence_facets
from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    FacetAssessment,
)


def _facet_plan(*queries: str) -> EvidenceQueryPlan:
    return EvidenceQueryPlan(
        original_query="compound fact question",
        facets=tuple(
            EvidenceFacet(index=index, query=query)
            for index, query in enumerate(queries)
        ),
        route="deterministic",
        confidence=0.6,
    )


def test_high_scoring_facet_cannot_consume_all_slots() -> None:
    plan = _facet_plan("username node-17", "password node-17")
    high = _candidate("username node-17 alice", fused_score=0.9)
    medium = _candidate("username node-17 bob", fused_score=0.6)
    low = _candidate("password node-17 secret", fused_score=0.3)

    selected, selection = select_evidence_facets(
        plan, {0: [high, medium], 1: [low]}, top_k=2
    )

    assert {candidate.chunk_id for candidate in selected} == {
        high.chunk_id,
        low.chunk_id,
    }
    assert selection.coverage[0].status == "covered"
    assert selection.coverage[1].status == "covered"


def test_shared_chunk_covers_two_facets_with_one_slot() -> None:
    plan = _facet_plan("username node-17", "password node-17")
    shared = _candidate(
        "node-17 username node-17 password node-17",
        fused_score=0.9,
    )

    selected, selection = select_evidence_facets(
        plan, {0: [shared], 1: [shared]}, top_k=1
    )

    assert len(selected) == 1
    assert selection.coverage[0].status == "covered"
    assert selection.coverage[1].status == "covered"


def test_budget_exhausted_when_top_k_less_than_facet_count() -> None:
    plan = _facet_plan("a node-17", "b node-17", "c node-17")
    a = _candidate("a node-17 one", fused_score=0.9)
    b = _candidate("b node-17 two", fused_score=0.8)
    c = _candidate("c node-17 three", fused_score=0.7)

    selected, selection = select_evidence_facets(
        plan, {0: [a], 1: [b], 2: [c]}, top_k=1
    )

    assert len(selected) == 1
    assert selection.coverage[0].status == "covered"
    assert selection.coverage[1].status == "unresolved"
    assert selection.coverage[1].reason == "budget_exhausted"
    assert selection.coverage[2].reason == "budget_exhausted"


def test_missing_support_is_unresolved_not_falsely_covered() -> None:
    plan = _facet_plan("username node-17", "password node-17")
    supporting = _candidate("username node-17 alice", fused_score=0.9)
    noise = _candidate("completely unrelated text", fused_score=0.8)

    selected, selection = select_evidence_facets(
        plan, {0: [supporting], 1: [noise]}, top_k=2
    )

    assert selection.coverage[0].status == "covered"
    assert selection.coverage[1].status == "unresolved"
    assert selection.coverage[1].reason == "no_supporting_evidence"


def test_valid_conflict_groups_produce_conflicting() -> None:
    plan = _facet_plan("password node-17")
    group_a = _candidate("password node-17 alpha", fused_score=0.9)
    group_b = _candidate("password node-17 beta", fused_score=0.8)

    class Assessor:
        def assess(self, plan, facet_index, candidates):
            return FacetAssessment(
                facet_index=0,
                supporting_chunk_ids=(group_a.chunk_id, group_b.chunk_id),
                conflict_groups=((group_a.chunk_id,), (group_b.chunk_id,)),
            )

    selected, selection = select_evidence_facets(
        plan, {0: [group_a, group_b]}, top_k=2, assessor=Assessor()
    )

    assert selection.coverage[0].status == "conflicting"
    assert len(selection.coverage[0].conflict_groups) == 2


def test_raising_assessor_falls_back_without_conflict_or_error() -> None:
    plan = _facet_plan("password node-17")
    candidate = _candidate("password node-17 alpha", fused_score=0.9)

    class RaisingAssessor:
        def assess(self, plan, facet_index, candidates):
            raise RuntimeError("assessor down")

    selected, selection = select_evidence_facets(
        plan, {0: [candidate]}, top_k=1, assessor=RaisingAssessor()
    )

    assert selection.coverage[0].status == "covered"
    assert selection.coverage[0].reason == "assessment_unavailable"


def test_assessment_with_unknown_chunk_ids_is_rejected() -> None:
    plan = _facet_plan("password node-17")
    candidate = _candidate("password node-17 alpha", fused_score=0.9)

    class BogusAssessor:
        def assess(self, plan, facet_index, candidates):
            return FacetAssessment(
                facet_index=0,
                supporting_chunk_ids=(uuid.uuid4(),),
                conflict_groups=((candidate.chunk_id,), (uuid.uuid4(),)),
            )

    selected, selection = select_evidence_facets(
        plan, {0: [candidate]}, top_k=1, assessor=BogusAssessor()
    )

    assert selection.coverage[0].status == "covered"
    assert selection.coverage[0].reason == "assessment_unavailable"


def test_selection_is_deterministic_under_tied_scores() -> None:
    plan = _facet_plan("username node-17")
    first = _candidate("username node-17 alice", fused_score=0.5)
    second = _candidate("username node-17 bob", fused_score=0.5)

    selected_a, _ = select_evidence_facets(plan, {0: [first, second], 1: []}, top_k=1)
    selected_b, _ = select_evidence_facets(plan, {0: [first, second], 1: []}, top_k=1)

    assert [candidate.chunk_id for candidate in selected_a] == [
        candidate.chunk_id for candidate in selected_b
    ]


def test_parent_row_overlap_keeps_single_representative() -> None:
    plan = _facet_plan("username node-17")
    document_id = uuid.uuid4()
    parent = _candidate(
        "username node-17 alice",
        fused_score=0.9,
        document_id=document_id,
        source_metadata={
            "table_index": 0,
            "table_chunk_type": "table",
            "data_row_start": 1,
            "data_row_end": 1,
        },
    )
    row = _candidate(
        "username node-17 alice row",
        fused_score=0.9,
        document_id=document_id,
        source_metadata={
            "table_index": 0,
            "table_chunk_type": "table_row",
            "data_row": 1,
        },
    )

    selected, _ = select_evidence_facets(plan, {0: [parent, row]}, top_k=2)

    assert len(selected) == 1
