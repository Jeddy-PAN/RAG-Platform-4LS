"""Bounded final-context selection for ordinary retrieval."""

from app.rag.retrieval.types import RetrievalCandidate


_PARENT_TYPES = {"table", "table_group"}


def _positive(metadata: dict, raw_key: str) -> bool:
    value = metadata.get(f"keyword_{raw_key}", metadata.get(raw_key, 0))
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _evidence_kind(candidate: RetrievalCandidate) -> str | None:
    metadata = candidate.score_metadata or {}
    if _positive(metadata, "exact_identifiers"):
        return "exact_identifier"
    if _positive(metadata, "contained_identifiers"):
        return "contained_identifier"
    return None


def _row_interval(candidate: RetrievalCandidate) -> tuple[int, int] | None:
    metadata = candidate.source_metadata or {}
    chunk_type = metadata.get("table_chunk_type")
    if chunk_type == "table_row":
        row = metadata.get("data_row")
        if isinstance(row, int):
            return row, row
    if chunk_type in _PARENT_TYPES:
        start = metadata.get("data_row_start")
        end = metadata.get("data_row_end")
        if isinstance(start, int) and isinstance(end, int):
            return start, end
    return None


def _structurally_overlaps(
    left: RetrievalCandidate,
    right: RetrievalCandidate,
) -> bool:
    left_metadata = left.source_metadata or {}
    right_metadata = right.source_metadata or {}
    if left.document_id != right.document_id:
        return False
    if left_metadata.get("table_index") is None or (
        left_metadata.get("table_index") != right_metadata.get("table_index")
    ):
        return False

    left_interval = _row_interval(left)
    right_interval = _row_interval(right)
    if left_interval is None or right_interval is None:
        return False

    left_type = left_metadata.get("table_chunk_type")
    right_type = right_metadata.get("table_chunk_type")
    if left_type == right_type == "table_row":
        return left_interval == right_interval
    if left_type in _PARENT_TYPES and right_type in _PARENT_TYPES:
        return left_interval == right_interval
    if left_type in _PARENT_TYPES or right_type in _PARENT_TYPES:
        return (
            left_interval[0] <= right_interval[0]
            and left_interval[1] >= right_interval[1]
        ) or (
            right_interval[0] <= left_interval[0]
            and right_interval[1] >= left_interval[1]
        )
    return False


def _deduplicate_structural(
    candidates: list[RetrievalCandidate],
) -> list[RetrievalCandidate]:
    indexed = list(enumerate(candidates))
    indexed.sort(
        key=lambda item: (
            0 if _evidence_kind(item[1]) == "exact_identifier" else 1,
            0 if _evidence_kind(item[1]) == "contained_identifier" else 1,
            item[0],
        )
    )

    representatives: list[RetrievalCandidate] = []
    representative_ids: set[object] = set()
    for _, candidate in indexed:
        if any(_structurally_overlaps(candidate, kept) for kept in representatives):
            continue
        representatives.append(candidate)
        representative_ids.add(candidate.chunk_id)
    return [candidate for candidate in candidates if candidate.chunk_id in representative_ids]


def select_evidence(
    candidates: list[RetrievalCandidate],
    top_k: int,
) -> list[RetrievalCandidate]:
    """Protect validated identifier evidence, then fill remaining ranked slots."""

    if top_k <= 0 or not candidates:
        return []

    deduplicated = _deduplicate_structural(candidates)
    protected: list[RetrievalCandidate] = []
    protected_groups: set[tuple[object, str]] = set()
    for evidence_kind in ("exact_identifier", "contained_identifier"):
        for candidate in deduplicated:
            if _evidence_kind(candidate) != evidence_kind:
                continue
            group = (candidate.document_id, evidence_kind)
            if group in protected_groups:
                continue
            protected_groups.add(group)
            protected.append(candidate)

    selected_ids = {candidate.chunk_id for candidate in protected[:top_k]}
    for candidate in deduplicated:
        if len(selected_ids) >= top_k:
            break
        selected_ids.add(candidate.chunk_id)

    results = [candidate for candidate in deduplicated if candidate.chunk_id in selected_ids]
    for rank, candidate in enumerate(results, start=1):
        evidence_kind = _evidence_kind(candidate)
        group = (candidate.document_id, evidence_kind) if evidence_kind else None
        protected_reason = (
            f"protected_{evidence_kind}"
            if group in protected_groups and candidate in protected[:top_k]
            else "ranked_fill"
        )
        candidate.rank = rank
        candidate.score_metadata = {
            **(candidate.score_metadata or {}),
            "evidence_selection_reason": protected_reason,
        }
    return results
