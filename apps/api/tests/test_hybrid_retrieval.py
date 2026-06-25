import uuid

from app.rag.retrieval.hybrid import fuse_retrieval_results, normalize_scores
from app.rag.retrieval.types import RetrievalCandidate


def test_normalize_scores_maps_values_to_zero_one() -> None:
    """Score normalization should preserve ordering in a simple range."""

    assert normalize_scores([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]
    assert normalize_scores([3.0, 3.0]) == [1.0, 1.0]


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
    assert next(result for result in results if result.chunk_id == chunk_c).vector_score is None
