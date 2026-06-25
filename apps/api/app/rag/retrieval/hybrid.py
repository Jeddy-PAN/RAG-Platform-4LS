from app.rag.retrieval.types import RetrievalCandidate


def normalize_scores(scores: list[float]) -> list[float]:
    """Normalize scores into 0..1 while preserving order."""

    if not scores:
        return []
    minimum = min(scores)
    maximum = max(scores)
    if maximum == minimum:
        return [1.0 for _ in scores]
    return [(score - minimum) / (maximum - minimum) for score in scores]


def fuse_retrieval_results(
    vector_candidates: list[RetrievalCandidate],
    keyword_candidates: list[RetrievalCandidate],
    top_k: int,
    vector_weight: float,
    keyword_weight: float,
) -> list[RetrievalCandidate]:
    """Merge vector and keyword candidates and compute weighted fused scores."""

    merged: dict[object, RetrievalCandidate] = {}
    for candidate in vector_candidates:
        merged[candidate.chunk_id] = candidate
    for candidate in keyword_candidates:
        existing = merged.get(candidate.chunk_id)
        if existing is None:
            merged[candidate.chunk_id] = candidate
        else:
            existing.keyword_score = candidate.keyword_score

    candidates = list(merged.values())
    vector_scores = [candidate.vector_score or 0.0 for candidate in candidates]
    keyword_scores = [candidate.keyword_score or 0.0 for candidate in candidates]
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

    candidates.sort(key=lambda candidate: candidate.fused_score or 0.0, reverse=True)
    results = candidates[:top_k]
    for index, candidate in enumerate(results, start=1):
        candidate.rank = index
    return results
