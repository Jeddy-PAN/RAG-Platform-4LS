import re
from dataclasses import dataclass
from typing import Protocol

from app.rag.retrieval.types import RetrievalCandidate


class RerankerProvider(Protocol):
    """Provider interface for ordering retrieved candidates by query relevance."""

    name: str

    def score(self, query: str, candidates: list[RetrievalCandidate]) -> list[float]:
        """Return one relevance score per candidate."""


@dataclass
class KeywordOverlapReranker:
    """Local lightweight reranker based on query-term overlap."""

    name: str = "keyword_overlap"

    def score(self, query: str, candidates: list[RetrievalCandidate]) -> list[float]:
        """Score candidates by normalized overlap with query terms."""

        query_terms = _tokenize(query)
        if not query_terms:
            return [0.0 for _ in candidates]
        query_set = set(query_terms)
        scores: list[float] = []
        for candidate in candidates:
            text_terms = set(_tokenize(candidate.text))
            overlap = len(query_set & text_terms)
            scores.append(overlap / len(query_set))
        return scores


def rerank_candidates(
    query: str,
    candidates: list[RetrievalCandidate],
    top_k: int,
    provider: RerankerProvider,
) -> list[RetrievalCandidate]:
    """Apply reranker scores, reorder candidates, and return the final top_k."""

    if not candidates:
        return []

    scored = list(zip(candidates, provider.score(query, candidates), strict=True))
    for pre_rank, (candidate, reranker_score) in enumerate(scored, start=1):
        candidate.score_metadata = {
            **candidate.score_metadata,
            "reranker": provider.name,
            "reranker_score": reranker_score,
            "pre_rerank_rank": candidate.rank or pre_rank,
            "pre_rerank_fused_score": candidate.fused_score,
        }

    scored.sort(
        key=lambda item: (
            item[1],
            item[0].fused_score if item[0].fused_score is not None else float("-inf"),
        ),
        reverse=True,
    )
    results = [candidate for candidate, _ in scored[:top_k]]
    for rank, candidate in enumerate(results, start=1):
        candidate.rank = rank
    return results


def _tokenize(text: str) -> list[str]:
    """Normalize text into simple lowercase word tokens."""

    return re.findall(r"[a-zA-Z0-9]+", text.lower())
