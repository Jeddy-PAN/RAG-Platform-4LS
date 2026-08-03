from dataclasses import replace

from app.rag.retrieval.types import RetrievalCandidate


_RAW_LEXICAL_METADATA = {
    "exact_identifiers",
    "exact_ascii_terms",
    "exact_cjk_terms",
    "contained_identifiers",
    "ngram_matches",
    "retrieval_mode",
}

DEFAULT_RRF_K = 60


def _stable_identity(candidate: RetrievalCandidate) -> tuple:
    return (
        candidate.document_name or "",
        candidate.chunk_index,
        str(candidate.document_id),
        str(candidate.chunk_id),
    )


def _route_ranks(
    candidates: list[RetrievalCandidate],
    score_attribute: str,
) -> dict[object, int]:
    """Assign competition ranks from one route, sharing ranks for score ties."""

    present = [
        candidate
        for candidate in candidates
        if getattr(candidate, score_attribute) is not None
    ]
    present.sort(
        key=lambda candidate: (
            -float(getattr(candidate, score_attribute)),
            *_stable_identity(candidate),
        )
    )

    ranks: dict[object, int] = {}
    previous_score: float | None = None
    current_rank = 0
    for position, candidate in enumerate(present, start=1):
        score = float(getattr(candidate, score_attribute))
        if previous_score is None or score != previous_score:
            current_rank = position
            previous_score = score
        ranks[candidate.chunk_id] = current_rank
    return ranks


def _namespace_keyword_metadata(meta: dict | None) -> dict:
    """Copy keyword metadata fields under ``keyword_*`` namespaced keys."""
    if not meta:
        return {}
    return {
        "keyword_exact_identifiers": meta.get("exact_identifiers", 0),
        "keyword_exact_ascii_terms": meta.get("exact_ascii_terms", 0),
        "keyword_exact_cjk_terms": meta.get("exact_cjk_terms", 0),
        "keyword_contained_identifiers": meta.get("contained_identifiers", 0),
        "keyword_ngram_matches": meta.get("ngram_matches", 0),
        "keyword_retrieval_mode": meta.get("retrieval_mode", "keyword"),
    }


def _copy_candidate(candidate: RetrievalCandidate) -> RetrievalCandidate:
    """Return a fusion-owned candidate without sharing mutable metadata dicts."""

    return replace(
        candidate,
        source_metadata=dict(candidate.source_metadata or {}),
        score_metadata=dict(candidate.score_metadata or {}),
    )


def fuse_retrieval_results(
    vector_candidates: list[RetrievalCandidate],
    keyword_candidates: list[RetrievalCandidate],
    top_k: int,
    vector_weight: float,
    keyword_weight: float,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[RetrievalCandidate]:
    """Merge vector and keyword candidates with stable weighted RRF.

    Lexical metadata from keyword candidates is namespaced under
    ``keyword_*`` keys for ALL keyword candidates, regardless of
    whether they overlap with a vector candidate.
    """

    merged: dict[object, RetrievalCandidate] = {}
    for candidate in vector_candidates:
        copied = _copy_candidate(candidate)
        merged[copied.chunk_id] = copied
    for source_candidate in keyword_candidates:
        candidate = _copy_candidate(source_candidate)
        keyword_metadata = _namespace_keyword_metadata(candidate.score_metadata)
        unrelated_metadata = {
            key: value
            for key, value in candidate.score_metadata.items()
            if key not in _RAW_LEXICAL_METADATA
        }
        candidate.score_metadata = {**unrelated_metadata, **keyword_metadata}

        existing = merged.get(candidate.chunk_id)
        if existing is None:
            merged[candidate.chunk_id] = candidate
        else:
            existing.keyword_score = candidate.keyword_score
            existing.score_metadata = {
                **existing.score_metadata,
                **candidate.score_metadata,
            }

    if rrf_k < 0:
        raise ValueError("rrf_k must be non-negative")

    candidates = list(merged.values())
    vector_ranks = _route_ranks(candidates, "vector_score")
    keyword_ranks = _route_ranks(candidates, "keyword_score")
    scale = rrf_k + 1

    for candidate in candidates:
        vector_rank = vector_ranks.get(candidate.chunk_id, 0)
        keyword_rank = keyword_ranks.get(candidate.chunk_id, 0)
        vector_contribution = (
            vector_weight * scale / (rrf_k + vector_rank)
            if vector_rank > 0
            else 0.0
        )
        keyword_contribution = (
            keyword_weight * scale / (rrf_k + keyword_rank)
            if keyword_rank > 0
            else 0.0
        )
        candidate.fused_score = vector_contribution + keyword_contribution
        candidate.score_metadata = {
            **candidate.score_metadata,
            "vector_rank": vector_rank,
            "keyword_rank": keyword_rank,
            "vector_rrf_score": vector_contribution,
            "keyword_rrf_score": keyword_contribution,
            "fusion_method": "weighted_rrf",
            "fusion_rrf_k": rrf_k,
        }

    candidates.sort(
        key=lambda candidate: (
            -(candidate.fused_score or 0.0),
            *_stable_identity(candidate),
        ),
    )
    results = candidates[:top_k]
    for index, candidate in enumerate(results, start=1):
        candidate.rank = index
    return results
