import uuid

from app.rag.retrieval.evidence_selection import select_evidence
from app.rag.retrieval.types import RetrievalCandidate


def _candidate(
    name: str,
    *,
    document_id: uuid.UUID,
    fused_score: float,
    score_metadata: dict | None = None,
    source_metadata: dict | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
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
