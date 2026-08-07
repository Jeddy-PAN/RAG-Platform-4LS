import uuid
import math
import pytest

from app.rag.retrieval.rerankers import (
    KeywordOverlapReranker,
    RerankerProviderError,
    rerank_candidates,
    rerank_with_fallback,
    validate_reranker_scores,
)
from app.rag.retrieval.types import RetrievalCandidate


def _candidate(text: str, fused_score: float) -> RetrievalCandidate:
    """Build a minimal candidate for reranker unit tests."""

    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="source.txt",
        chunk_index=0,
        text=text,
        source_metadata={},
        fused_score=fused_score,
    )


def test_keyword_overlap_reranker_reorders_candidates_by_query_terms() -> None:
    """Keyword overlap reranking should promote semantically closer candidate text."""

    weak = _candidate("general processor announcement", 0.9)
    strong = _candidate("google sycamore quantum supremacy benchmark", 0.4)

    results = rerank_candidates(
        "What did Google Sycamore claim about quantum supremacy?",
        [weak, strong],
        top_k=2,
        provider=KeywordOverlapReranker(),
    )

    assert results == [strong, weak]
    assert [candidate.rank for candidate in results] == [1, 2]
    assert strong.score_metadata["reranker"] == "keyword_overlap"
    assert strong.score_metadata["reranker_score"] > weak.score_metadata["reranker_score"]
    assert strong.score_metadata["pre_rerank_rank"] == 2


def test_reranking_can_limit_candidates_after_reordering() -> None:
    """Reranking should sort a wider candidate set before applying final top_k."""

    weak = _candidate("alpha", 0.99)
    strong = _candidate("target phrase target phrase", 0.1)

    results = rerank_candidates(
        "target phrase",
        [weak, strong],
        top_k=1,
        provider=KeywordOverlapReranker(),
    )

    assert results == [strong]
    assert results[0].rank == 1


def test_reranker_scores_search_text_and_returns_original_candidate() -> None:
    """Reranking uses search_text for scoring but returns the original payload."""

    chunk_id = uuid.uuid4()
    candidate = RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        document_name="systems.docx",
        chunk_index=0,
        text="alpha payload row",
        search_text="Document: systems.docx\nContent:\nalpha payload row",
        source_metadata={},
    )

    results = rerank_candidates(
        "systems",
        [candidate],
        top_k=1,
        provider=KeywordOverlapReranker(),
    )

    assert len(results) == 1
    assert results[0].chunk_id == chunk_id
    assert results[0].text == "alpha payload row"
    assert results[0].score_metadata["reranker_score"] == 1.0


@pytest.mark.parametrize(
    "scores",
    [[], ["bad"], [True], [math.nan], [math.inf]],
)
def test_validate_reranker_scores_rejects_invalid_responses(scores) -> None:
    with pytest.raises(RerankerProviderError):
        validate_reranker_scores(scores, expected_count=1)


def test_rerank_candidates_validates_before_mutating_candidates() -> None:
    candidate = _candidate("synthetic payload", 0.4)

    class Provider:
        name = "synthetic"

        def score(self, query, candidates):
            return ["invalid"]

    with pytest.raises(RerankerProviderError):
        rerank_candidates("synthetic query", [candidate], 1, Provider())

    assert candidate.score_metadata == {}
    assert candidate.rank is None


def test_rerank_with_fallback_preserves_cjk_lexical_order() -> None:
    weak = _candidate("普通说明", 0.9)
    relevant = _candidate("服务器用户名 node17", 0.1)

    class Provider:
        name = "multilingual_cross_encoder"

        def score(self, query, candidates):
            raise RerankerProviderError("redacted")

    outcome = rerank_with_fallback(
        "服务器用户名 node17",
        [weak, relevant],
        top_k=1,
        provider=Provider(),
    )

    assert outcome.fallback is True
    assert outcome.fallback_reason == "response_invalid"
    assert outcome.results == [relevant]
    assert relevant.score_metadata["reranker"] == "keyword_overlap"


def test_facet_reranker_metadata_keeps_scores_for_shared_candidate() -> None:
    candidate = _candidate("shared node17 attribute", 0.4)

    class Provider:
        name = "multilingual_cross_encoder"

        def score(self, query, candidates):
            return [0.7 if query == "first" else 0.3]

    rerank_candidates("first", [candidate], 1, Provider(), facet_index=0)
    rerank_candidates("second", [candidate], 1, Provider(), facet_index=1)

    assert candidate.score_metadata["facet_reranker_scores"] == {"0": 0.7, "1": 0.3}
    assert candidate.score_metadata["facet_reranker_ranks"] == {"0": 1, "1": 1}
