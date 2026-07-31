import uuid
from copy import deepcopy

from app.rag.retrieval.hybrid import fuse_retrieval_results, normalize_scores
from app.rag.retrieval.types import RetrievalCandidate


def test_normalize_scores_maps_values_to_zero_one() -> None:
    """Score normalization should preserve ordering in a simple range."""

    assert normalize_scores([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]
    assert normalize_scores([3.0, 3.0]) == [1.0, 1.0]


def test_normalize_scores_distinguishes_missing_from_real_zero() -> None:
    assert normalize_scores([None, None]) == [0.0, 0.0]
    assert normalize_scores([0.0, None]) == [1.0, 0.0]
    assert normalize_scores([-0.5, None]) == [1.0, 0.0]


def test_hybrid_fusion_merges_candidates_by_chunk_id() -> None:
    """Hybrid fusion should combine vector and keyword evidence per chunk."""

    chunk_a = uuid.uuid4()
    chunk_b = uuid.uuid4()
    chunk_c = uuid.uuid4()
    document_id = uuid.uuid4()
    vector_candidates = [
        RetrievalCandidate(
            chunk_id=chunk_a,
            document_id=document_id,
            document_name="doc.txt",
            chunk_index=0,
            text="alpha vector",
            source_metadata={},
            vector_score=0.9,
        ),
        RetrievalCandidate(
            chunk_id=chunk_b,
            document_id=document_id,
            document_name="doc.txt",
            chunk_index=1,
            text="beta vector",
            source_metadata={},
            vector_score=0.5,
        ),
    ]
    keyword_candidates = [
        RetrievalCandidate(
            chunk_id=chunk_a,
            document_id=document_id,
            document_name="doc.txt",
            chunk_index=0,
            text="alpha vector",
            source_metadata={},
            keyword_score=0.4,
        ),
        RetrievalCandidate(
            chunk_id=chunk_c,
            document_id=document_id,
            document_name="doc.txt",
            chunk_index=2,
            text="gamma keyword",
            source_metadata={},
            keyword_score=0.8,
        ),
    ]

    results = fuse_retrieval_results(
        vector_candidates,
        keyword_candidates,
        top_k=3,
        vector_weight=0.5,
        keyword_weight=0.5,
    )

    assert [result.rank for result in results] == [1, 2, 3]
    assert {result.chunk_id for result in results} == {chunk_a, chunk_b, chunk_c}
    assert results[0].fused_score >= results[-1].fused_score


def test_hybrid_fusion_preserves_keyword_metadata() -> None:
    """Lexical metadata from keyword retrieval survives hybrid fusion."""
    from app.rag.retrieval.hybrid import fuse_retrieval_results
    import uuid

    cid = uuid.uuid4()
    did = uuid.uuid4()
    v = RetrievalCandidate(chunk_id=cid, document_id=did, document_name="d.txt",
                           chunk_index=0, text="srv active", source_metadata={}, vector_score=0.9)
    kw = RetrievalCandidate(chunk_id=cid, document_id=did, document_name="d.txt",
                            chunk_index=0, text="srv active", source_metadata={}, keyword_score=5.0,
                            score_metadata={"retrieval_mode": "keyword", "exact_identifiers": 1,
                                            "exact_ascii_terms": 2, "exact_cjk_terms": 0,
                                            "contained_identifiers": 0, "ngram_matches": 0})
    results = fuse_retrieval_results([v], [kw], top_k=5, vector_weight=0.5, keyword_weight=0.5)
    assert len(results) == 1
    meta = results[0].score_metadata or {}
    assert meta.get("keyword_exact_identifiers") == 1
    assert meta.get("keyword_exact_ascii_terms") == 2
    assert meta.get("keyword_ngram_matches") == 0
    assert meta.get("normalized_keyword_score") is not None


def test_hybrid_fusion_does_not_mutate_input_candidates() -> None:
    chunk_id = uuid.uuid4()
    document_id = uuid.uuid4()
    vector = RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=document_id,
        document_name="source.txt",
        chunk_index=0,
        text="node01-east",
        source_metadata={"page": 1},
        vector_score=0.5,
        score_metadata={"retrieval_mode": "vector"},
    )
    keyword = RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=document_id,
        document_name="source.txt",
        chunk_index=0,
        text="node01-east",
        source_metadata={"page": 1},
        keyword_score=5.0,
        score_metadata={"retrieval_mode": "keyword", "exact_identifiers": 1},
    )
    vector_before = deepcopy(vector)
    keyword_before = deepcopy(keyword)

    fuse_retrieval_results(
        [vector], [keyword], top_k=1, vector_weight=0.5, keyword_weight=0.5,
    )

    assert vector == vector_before
    assert keyword == keyword_before


def test_hybrid_fusion_uses_same_complete_keyword_schema_for_both_paths() -> None:
    document_id = uuid.uuid4()
    overlap_id = uuid.uuid4()
    keyword_only_id = uuid.uuid4()
    lexical_metadata = {
        "retrieval_mode": "keyword",
        "exact_identifiers": 1,
        "exact_ascii_terms": 2,
        "exact_cjk_terms": 3,
        "contained_identifiers": 4,
        "ngram_matches": 5,
        "diagnostic": "preserved",
    }
    vector = RetrievalCandidate(
        chunk_id=overlap_id,
        document_id=document_id,
        document_name="source.txt",
        chunk_index=0,
        text="overlap",
        source_metadata={},
        vector_score=0.5,
    )
    keywords = [
        RetrievalCandidate(
            chunk_id=chunk_id,
            document_id=document_id,
            document_name="source.txt",
            chunk_index=index,
            text="keyword",
            source_metadata={},
            keyword_score=5.0,
            score_metadata=dict(lexical_metadata),
        )
        for index, chunk_id in enumerate((overlap_id, keyword_only_id))
    ]

    results = fuse_retrieval_results(
        [vector], keywords, top_k=2, vector_weight=0.5, keyword_weight=0.5,
    )

    required = {
        "keyword_exact_identifiers",
        "keyword_exact_ascii_terms",
        "keyword_exact_cjk_terms",
        "keyword_contained_identifiers",
        "keyword_ngram_matches",
        "keyword_retrieval_mode",
        "normalized_keyword_score",
    }
    for result in results:
        metadata = result.score_metadata
        assert required <= metadata.keys()
        assert metadata["diagnostic"] == "preserved"
        assert not {
            "exact_identifiers",
            "exact_ascii_terms",
            "exact_cjk_terms",
            "contained_identifiers",
            "ngram_matches",
            "retrieval_mode",
        } & metadata.keys()


def test_hybrid_fusion_orders_equal_scores_by_stable_identity() -> None:
    high_id = uuid.UUID(int=2)
    low_id = uuid.UUID(int=1)
    document_id = uuid.uuid4()

    def candidate(chunk_id: uuid.UUID) -> RetrievalCandidate:
        return RetrievalCandidate(
            chunk_id=chunk_id,
            document_id=document_id,
            document_name="same.txt",
            chunk_index=0,
            text="equal",
            source_metadata={},
            keyword_score=1.0,
        )

    results = fuse_retrieval_results(
        [], [candidate(high_id), candidate(low_id)],
        top_k=2, vector_weight=0.5, keyword_weight=0.5,
    )

    assert [result.chunk_id for result in results] == [low_id, high_id]


def test_hybrid_fusion_marks_absent_modalities_without_inventing_evidence() -> None:
    document_id = uuid.uuid4()

    def candidate(
        *, vector_score: float | None = None, keyword_score: float | None = None,
    ) -> RetrievalCandidate:
        return RetrievalCandidate(
            chunk_id=uuid.uuid4(),
            document_id=document_id,
            document_name="source.txt",
            chunk_index=0,
            text="evidence",
            source_metadata={},
            vector_score=vector_score,
            keyword_score=keyword_score,
        )

    keyword_only = fuse_retrieval_results(
        [], [candidate(keyword_score=5.0)],
        top_k=1, vector_weight=0.5, keyword_weight=0.5,
    )[0]
    assert keyword_only.vector_score is None
    assert keyword_only.score_metadata["normalized_vector_score"] == 0.0
    assert keyword_only.score_metadata["normalized_keyword_score"] == 1.0

    vector_only = fuse_retrieval_results(
        [candidate(vector_score=0.0)], [],
        top_k=1, vector_weight=0.5, keyword_weight=0.5,
    )[0]
    assert vector_only.keyword_score is None
    assert vector_only.score_metadata["normalized_vector_score"] == 1.0
    assert vector_only.score_metadata["normalized_keyword_score"] == 0.0


def test_exact_keyword_evidence_stays_above_sibling_through_fusion() -> None:
    document_id = uuid.uuid4()

    def candidate(name: str, score: float) -> RetrievalCandidate:
        return RetrievalCandidate(
            chunk_id=uuid.uuid4(),
            document_id=document_id,
            document_name=f"{name}.txt",
            chunk_index=0,
            text=name,
            source_metadata={},
            keyword_score=score,
        )

    results = fuse_retrieval_results(
        [], [candidate("exact", 7.0), candidate("sibling", 4.0)],
        top_k=2, vector_weight=0.5, keyword_weight=0.5,
    )

    assert [result.document_name for result in results] == ["exact.txt", "sibling.txt"]
    assert results[0].fused_score > results[1].fused_score
