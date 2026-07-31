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


def normalize_scores(scores: list[float | None]) -> list[float]:
    """Normalize present scores into 0..1 and map missing scores to zero."""

    if not scores:
        return []

    present_scores = [float(score) for score in scores if score is not None]
    if not present_scores:
        return [0.0 for _ in scores]

    minimum = min(present_scores)
    maximum = max(present_scores)
    if maximum == minimum:
        normalized_present = iter([1.0 for _ in present_scores])
    else:
        normalized_present = iter(
            (score - minimum) / (maximum - minimum) for score in present_scores
        )
    return [0.0 if score is None else next(normalized_present) for score in scores]


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
) -> list[RetrievalCandidate]:
    """Merge vector and keyword candidates and compute weighted fused scores.

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

    candidates = list(merged.values())
    vector_scores = [candidate.vector_score for candidate in candidates]
    keyword_scores = [candidate.keyword_score for candidate in candidates]
    normalized_vectors = normalize_scores(vector_scores)
    normalized_keywords = normalize_scores(keyword_scores)

    for candidate, normalized_vector, normalized_keyword in zip(
        candidates,
        normalized_vectors,
        normalized_keywords,
        strict=True,
    ):
        candidate.fused_score = (
            vector_weight * normalized_vector + keyword_weight * normalized_keyword
        )
        candidate.score_metadata = {
            **candidate.score_metadata,
            "normalized_vector_score": normalized_vector,
            "normalized_keyword_score": normalized_keyword,
        }

    candidates.sort(
        key=lambda candidate: (
            -(candidate.fused_score or 0.0),
            candidate.document_name or "",
            candidate.chunk_index,
            str(candidate.document_id),
            str(candidate.chunk_id),
        ),
    )
    results = candidates[:top_k]
    for index, candidate in enumerate(results, start=1):
        candidate.rank = index
    return results
