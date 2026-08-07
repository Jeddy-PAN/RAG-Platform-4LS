import re
from dataclasses import dataclass
import math
import time
from typing import Protocol
from collections.abc import Sequence

from app.rag.retrieval.types import RetrievalCandidate
from app.rag.retrieval.lexical import score_chunk, tokenize


class RerankerProviderError(RuntimeError):
    """A provider or provider-response failure safe for retrieval fallback."""


class RerankerTransportError(RerankerProviderError):
    """A transport-level failure that should be logged as unavailable."""


def validate_reranker_scores(
    scores: Sequence[object],
    expected_count: int,
) -> list[float]:
    """Validate a provider response without exposing response contents."""

    if len(scores) != expected_count:
        raise RerankerProviderError("Reranker response count mismatch")
    normalized: list[float] = []
    for score in scores:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RerankerProviderError("Reranker response contains a non-numeric score")
        value = float(score)
        if not math.isfinite(value):
            raise RerankerProviderError("Reranker response contains a non-finite score")
        normalized.append(value)
    return normalized


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

        query_terms = tokenize(query)
        scores: list[float] = []
        for candidate in candidates:
            score, _, _ = score_chunk(
                query_terms,
                tokenize(candidate.search_text or candidate.text),
            )
            scores.append(float(score))
        return scores


def rerank_candidates(
    query: str,
    candidates: list[RetrievalCandidate],
    top_k: int,
    provider: RerankerProvider,
    facet_index: int | None = None,
) -> list[RetrievalCandidate]:
    """Apply reranker scores, reorder candidates, and return the final top_k."""

    if not candidates:
        return []

    scores = validate_reranker_scores(provider.score(query, candidates), len(candidates))
    scored = list(zip(candidates, scores, strict=True))
    for pre_rank, (candidate, reranker_score) in enumerate(scored, start=1):
        metadata = dict(candidate.score_metadata or {})
        if facet_index is None:
            metadata.update(
                {
                    "reranker": provider.name,
                    "reranker_score": reranker_score,
                    "pre_rerank_rank": candidate.rank or pre_rank,
                    "pre_rerank_fused_score": candidate.fused_score,
                }
            )
        else:
            facet_scores = dict(metadata.get("facet_reranker_scores") or {})
            facet_ranks = dict(metadata.get("facet_reranker_ranks") or {})
            facet_scores[str(facet_index)] = reranker_score
            facet_ranks[str(facet_index)] = pre_rank
            metadata.update(
                {
                    "reranker": provider.name,
                    "facet_reranker_scores": facet_scores,
                    "facet_reranker_ranks": facet_ranks,
                }
            )
        candidate.score_metadata = {
            **metadata,
        }

    scored.sort(
        key=lambda item: (
            -item[1],
            -(item[0].fused_score if item[0].fused_score is not None else float("-inf")),
            str(item[0].chunk_id),
        )
    )
    results = [candidate for candidate, _ in scored[:top_k]]
    for rank, candidate in enumerate(results, start=1):
        candidate.rank = rank
    return results


@dataclass(frozen=True)
class RerankOutcome:
    results: list[RetrievalCandidate]
    provider_name: str | None
    candidate_count: int
    latency_ms: int
    fallback: bool
    fallback_reason: str | None = None


def rerank_with_fallback(
    query: str,
    candidates: list[RetrievalCandidate],
    top_k: int,
    provider: RerankerProvider | None,
    *,
    facet_index: int | None = None,
    fallback_reason_override: str | None = None,
    provider_name_override: str | None = None,
) -> RerankOutcome:
    """Apply a provider and conservatively fall back to local lexical ranking."""

    started = time.perf_counter()
    if provider is None:
        fallback_reason = "provider_disabled"
        fallback_provider: RerankerProvider = KeywordOverlapReranker()
        results = rerank_candidates(
            query, candidates, top_k, fallback_provider, facet_index=facet_index
        )
        return RerankOutcome(
            results, provider_name_override or fallback_provider.name, len(candidates),
            int((time.perf_counter() - started) * 1000), True,
            fallback_reason_override or fallback_reason,
        )
    try:
        results = rerank_candidates(
            query, candidates, top_k, provider, facet_index=facet_index
        )
        return RerankOutcome(
            results, provider.name, len(candidates),
            int((time.perf_counter() - started) * 1000), False, None,
        )
    except RerankerTransportError:
        fallback_provider = KeywordOverlapReranker()
        results = rerank_candidates(
            query, candidates, top_k, fallback_provider, facet_index=facet_index
        )
        return RerankOutcome(
            results, provider.name, len(candidates),
            int((time.perf_counter() - started) * 1000), True, "provider_unavailable",
        )
    except RerankerProviderError:
        fallback_provider = KeywordOverlapReranker()
        results = rerank_candidates(
            query, candidates, top_k, fallback_provider, facet_index=facet_index
        )
        return RerankOutcome(
            results, provider.name, len(candidates),
            int((time.perf_counter() - started) * 1000), True, "response_invalid",
        )
    except (TimeoutError, ConnectionError):
        fallback_provider = KeywordOverlapReranker()
        results = rerank_candidates(
            query, candidates, top_k, fallback_provider, facet_index=facet_index
        )
        return RerankOutcome(
            results, provider.name, len(candidates),
            int((time.perf_counter() - started) * 1000), True, "provider_unavailable",
        )


def _tokenize(text: str) -> list[str]:
    """Normalize text into simple lowercase word tokens."""

    return re.findall(r"[a-zA-Z0-9]+", text.lower())
