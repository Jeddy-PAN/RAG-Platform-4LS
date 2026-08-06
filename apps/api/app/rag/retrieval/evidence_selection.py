"""Bounded final-context selection for ordinary retrieval."""

import re
from dataclasses import replace

from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    EvidenceSelectionPlan,
    FacetAssessment,
    FacetEvidenceCoverage,
)
from app.rag.retrieval.lexical import tokenize
from app.rag.retrieval.types import RetrievalCandidate


_PARENT_TYPES = {"table", "table_group"}
_SURFACE_TOKEN = re.compile(
    r"[a-z0-9]+(?:[._\-/+:][a-z0-9]+)*|[\u3400-\u9fff]+",
    re.IGNORECASE,
)
_GENERIC_QUERY_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "find",
    "get",
    "give",
    "is",
    "list",
    "of",
    "show",
    "the",
    "to",
    "what",
    "which",
    "with",
    "请",
    "查找",
    "查询",
    "获取",
    "列出",
    "和",
    "的",
    "请问",
}


def _positive(metadata: dict, raw_key: str) -> bool:
    for key in (raw_key, f"keyword_{raw_key}"):
        if key not in metadata:
            continue
        try:
            if float(metadata[key]) > 0:
                return True
        except (TypeError, ValueError):
            continue
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


# ── Round 4B facet-aware evidence coverage ─────────────────────────


def _surface_terms(text: str) -> set[str]:
    """Return case-folded terms while preserving identifier punctuation."""

    terms: set[str] = set()
    for match in _SURFACE_TOKEN.finditer(text or ""):
        value = match.group(0).casefold()
        terms.add(value)
        if value and all("\u3400" <= char <= "\u9fff" for char in value):
            terms.update(value[index : index + 2] for index in range(len(value) - 1))
    return terms


def _positive_any(metadata: dict, *keys: str) -> bool:
    return any(_positive(metadata, key) for key in keys)


def _entity_terms(facet: EvidenceFacet) -> set[str]:
    explicit = {
        term
        for entity in facet.entities
        for term in _surface_terms(entity.text)
    }
    if explicit:
        return explicit
    return set(tokenize(facet.query).identifier_terms)


def _attribute_terms(facet: EvidenceFacet, entity_terms: set[str]) -> set[str]:
    if facet.attributes:
        return {
            term
            for attribute in facet.attributes
            for term in _surface_terms(attribute)
        }
    terms = {
        term
        for term in _surface_terms(facet.query)
        if term not in entity_terms and term not in _GENERIC_QUERY_WORDS
    }
    if terms:
        return terms
    return {
        term
        for term in _surface_terms(facet.query)
        if term not in entity_terms
    }


def _contains_cjk_attribute(attribute: str, text: str) -> bool:
    """Match a CJK phrase inside a longer sentence-level CJK run."""

    if not attribute or not all("\u3400" <= char <= "\u9fff" for char in attribute):
        return False
    return any(
        attribute.casefold() in match.group(0).casefold()
        for match in re.finditer(r"[\u3400-\u9fff]+", text or "")
    )


def _facet_support_features(
    facet: EvidenceFacet,
    candidate: RetrievalCandidate,
) -> dict[str, object]:
    """Separate entity consistency from requested-attribute evidence."""

    metadata = candidate.score_metadata or {}
    candidate_terms = _surface_terms(candidate.search_text or candidate.text)
    entity_terms = _entity_terms(facet)
    attribute_terms = _attribute_terms(facet, entity_terms)
    entity_matches = entity_terms & candidate_terms
    entity_metadata = _positive_any(
        metadata,
        "exact_identifiers",
        "contained_identifiers",
    )
    entity_consistent = not entity_terms or bool(entity_matches) or entity_metadata
    attribute_evidence = bool(attribute_terms) and attribute_terms <= candidate_terms
    if not attribute_evidence and facet.attributes:
        cjk_attributes = [
            attribute.casefold()
            for attribute in facet.attributes
            if attribute and all("\u3400" <= char <= "\u9fff" for char in attribute)
        ]
        if cjk_attributes and all(
            _contains_cjk_attribute(attribute, candidate.search_text or candidate.text)
            for attribute in cjk_attributes
        ):
            non_cjk_terms = {
                term
                for term in attribute_terms
                if not all("\u3400" <= char <= "\u9fff" for char in term)
            }
            attribute_evidence = non_cjk_terms <= candidate_terms
    identifier_strength = (
        2.0
        if _positive_any(metadata, "exact_identifiers")
        else 1.0
        if _positive_any(metadata, "contained_identifiers")
        else 0.0
    )
    return {
        "entity_consistent": entity_consistent,
        "attribute_evidence": attribute_evidence,
        "support": entity_consistent and attribute_evidence,
        "support_strength": (
            (2.0 if attribute_evidence else 0.0)
            + (1.0 if entity_matches else 0.0)
            + identifier_strength
        ),
    }


def _facet_support_score(
    facet: EvidenceFacet,
    candidate: RetrievalCandidate,
) -> float:
    """Return zero unless the candidate proves the requested facet."""

    features = _facet_support_features(facet, candidate)
    return float(features["support_strength"]) if features["support"] else 0.0


def _stable_score_key(candidate) -> tuple:
    """Descending fused/keyword/vector score with a stable chunk-id tiebreak."""

    score = candidate.fused_score
    if score is None:
        score = candidate.keyword_score
    if score is None:
        score = candidate.vector_score
    return (-float(score or 0.0), str(candidate.chunk_id))


def _best_for_facet(
    facet: EvidenceFacet,
    candidates: list[RetrievalCandidate],
) -> RetrievalCandidate | None:
    """Best supporting candidate for one facet under a stable ordering."""

    supporting = [c for c in candidates if _facet_support_score(facet, c) > 0]
    if not supporting:
        return None
    return sorted(
        supporting,
        key=lambda candidate: (
            -_facet_support_score(facet, candidate),
            *_stable_score_key(candidate),
        ),
    )[0]


def _valid_assessment(
    assessment: FacetAssessment | None,
    facet_index: int,
    facet_ids: set[object],
) -> bool:
    """Reject malformed or ungrounded assessor output."""

    try:
        if not isinstance(assessment, FacetAssessment):
            return False
        if assessment.facet_index != facet_index:
            return False
        ids = list(assessment.supporting_chunk_ids)
        if len(ids) != len(set(ids)) or not set(ids) <= facet_ids:
            return False
        group_ids: set[object] = set()
        for group in assessment.conflict_groups:
            if not group or len(group) != len(set(group)):
                return False
            if group_ids & set(group):
                return False
            group_ids.update(group)
            ids.extend(group)
        return set(ids) <= facet_ids and group_ids <= set(assessment.supporting_chunk_ids)
    except (AttributeError, TypeError):
        return False


def _merge_metadata(left: dict, right: dict) -> dict:
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if key == "evidence_facet_indexes":
            existing = merged.get(key, [])
            merged[key] = sorted(set(existing or []) | set(value or []))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            existing = merged.get(key)
            if isinstance(existing, (int, float)) and not isinstance(existing, bool):
                merged[key] = max(existing, value)
            elif existing is None:
                merged[key] = value
        elif key not in merged:
            merged[key] = value
        elif isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = list(dict.fromkeys([*merged[key], *value]))
    return merged


def _merge_candidate(
    left: RetrievalCandidate,
    right: RetrievalCandidate,
) -> RetrievalCandidate:
    """Merge one chunk returned by several facet routes without shared mutation."""

    preferred = min((left, right), key=_stable_score_key)

    def best_score(name: str) -> float | None:
        values = [getattr(left, name), getattr(right, name)]
        values = [value for value in values if value is not None]
        return max(values) if values else None

    return replace(
        preferred,
        vector_score=best_score("vector_score"),
        keyword_score=best_score("keyword_score"),
        fused_score=best_score("fused_score"),
        score_metadata=_merge_metadata(left.score_metadata, right.score_metadata),
    )


def _canonicalize_facet_candidates(
    candidates_by_facet: dict[int, list[RetrievalCandidate]],
) -> dict[int, list[RetrievalCandidate]]:
    """Merge repeated chunk IDs, then apply structural dedup per facet."""

    canonical: dict[object, RetrievalCandidate] = {}
    for candidates in candidates_by_facet.values():
        for candidate in candidates:
            existing = canonical.get(candidate.chunk_id)
            canonical[candidate.chunk_id] = (
                replace(candidate, score_metadata=dict(candidate.score_metadata or {}))
                if existing is None
                else _merge_candidate(existing, candidate)
            )

    deduped: dict[int, list[RetrievalCandidate]] = {}
    for facet_index, candidates in candidates_by_facet.items():
        pool = [canonical[candidate.chunk_id] for candidate in candidates]
        deduped[facet_index] = _deduplicate_structural(pool)
    return deduped


def select_evidence_facets(
    evidence_plan: EvidenceQueryPlan,
    candidates_by_facet: dict[int, list[RetrievalCandidate]],
    top_k: int,
    assessor=None,
) -> tuple[list[RetrievalCandidate], EvidenceSelectionPlan]:
    """Select bounded ordinary evidence while reserving per-facet coverage.

    Reserves at least one distinct supporting chunk per supported facet before
    ranked fill, never exceeds ``top_k``, and records explicit coverage statuses.
    """
    if top_k <= 0:
        coverage = tuple(
            FacetEvidenceCoverage(
                facet_index=facet.index,
                status="unresolved",
                reason="budget_exhausted",
            )
            for facet in evidence_plan.facets
        )
        return [], EvidenceSelectionPlan(query_plan=evidence_plan, coverage=coverage)

    deduped_by_facet = _canonicalize_facet_candidates(candidates_by_facet)
    membership: dict[object, set[int]] = {}
    for facet_index, candidates in deduped_by_facet.items():
        for candidate in candidates:
            membership.setdefault(candidate.chunk_id, set()).add(facet_index)

    facet_by_index = {facet.index: facet for facet in evidence_plan.facets}
    facet_ids = {
        facet_index: {candidate.chunk_id for candidate in candidates}
        for facet_index, candidates in deduped_by_facet.items()
    }
    assessments: dict[int, FacetAssessment] = {}
    assessment_support_ids: dict[int, set[object]] = {}
    assessment_unavailable: set[int] = set()
    if assessor is not None:
        for facet in evidence_plan.facets:
            pool = deduped_by_facet.get(facet.index, [])
            if not pool:
                continue
            try:
                assessment = assessor.assess(evidence_plan, facet.index, pool)
            except Exception:
                assessment = None
            if not _valid_assessment(assessment, facet.index, facet_ids.get(facet.index, set())):
                assessment_unavailable.add(facet.index)
                continue
            assessments[facet.index] = assessment
            assessment_support_ids[facet.index] = set(assessment.supporting_chunk_ids)

    deterministic_support_ids: dict[int, set[object]] = {}
    supported: list[int] = []
    for facet in evidence_plan.facets:
        pool = deduped_by_facet.get(facet.index, [])
        deterministic_support_ids[facet.index] = {
            candidate.chunk_id
            for candidate in pool
            if _facet_support_score(facet, candidate) > 0
        }
        support_ids = deterministic_support_ids[facet.index] | assessment_support_ids.get(
            facet.index, set()
        )
        if support_ids:
            supported.append(facet.index)

    selected: list[RetrievalCandidate] = []
    selected_ids: set[object] = set()
    reserved_facets: set[int] = set()
    conflict_ready: set[int] = set()
    conflict_budget_exhausted: set[int] = set()

    for facet_index in supported:
        facet = facet_by_index[facet_index]
        pool = deduped_by_facet.get(facet_index, [])
        best = _best_for_facet(facet, pool)
        if best is None:
            assessed_ids = assessment_support_ids.get(facet_index, set())
            assessed_candidates = [
                candidate for candidate in pool if candidate.chunk_id in assessed_ids
            ]
            best = sorted(assessed_candidates, key=_stable_score_key)[0] if assessed_candidates else None
        if best is None:
            continue
        if best.chunk_id not in selected_ids:
            if len(selected) >= top_k:
                continue
            selected.append(best)
            selected_ids.add(best.chunk_id)
        reserved_facets.add(facet_index)

    # Every supported facet gets its base representative before any conflict
    # group consumes additional budget.  A conflict is terminal only when all
    # validated groups can be represented after those reservations.
    for facet_index, assessment in assessments.items():
        if len(assessment.conflict_groups) < 2:
            continue
        group_candidates: list[RetrievalCandidate] = []
        for group in assessment.conflict_groups:
            candidates = [
                candidate
                for candidate in deduped_by_facet.get(facet_index, [])
                if candidate.chunk_id in group
            ]
            if not candidates:
                group_candidates = []
                break
            group_candidates.append(sorted(candidates, key=_stable_score_key)[0])
        required_new_ids = {
            candidate.chunk_id
            for candidate in group_candidates
            if candidate.chunk_id not in selected_ids
        }
        if not group_candidates or len(selected) + len(required_new_ids) > top_k:
            conflict_budget_exhausted.add(facet_index)
            continue
        for candidate in group_candidates:
            if candidate.chunk_id not in selected_ids:
                selected.append(candidate)
                selected_ids.add(candidate.chunk_id)
        conflict_ready.add(facet_index)

    remaining = top_k - len(selected)
    if remaining > 0:
        fill_by_id = {
            candidate.chunk_id: candidate
            for pool in deduped_by_facet.values()
            for candidate in pool
            if candidate.chunk_id not in selected_ids
        }
        fill_pool = list(fill_by_id.values())
        fill_pool.sort(key=_stable_score_key)
        for candidate in fill_pool:
            if len(selected) >= top_k or candidate.chunk_id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate.chunk_id)

    for rank, candidate in enumerate(selected, start=1):
        candidate.rank = rank
        facet_indexes = sorted(membership.get(candidate.chunk_id, set()))
        reserved = any(index in reserved_facets for index in facet_indexes)
        candidate.score_metadata = {
            **(candidate.score_metadata or {}),
            "evidence_selection_reason": "facet_reserved" if reserved else "ranked_fill",
            "evidence_facet_indexes": facet_indexes,
        }

    coverage: list[FacetEvidenceCoverage] = []
    for facet in evidence_plan.facets:
        facet_index = facet.index
        facet_support_ids = deterministic_support_ids.get(facet_index, set()) | assessment_support_ids.get(
            facet_index, set()
        )
        facet_selected = [
            candidate
            for candidate in selected
            if facet_index in membership.get(candidate.chunk_id, set())
            and candidate.chunk_id in facet_support_ids
        ]
        if facet_index in conflict_ready:
            coverage.append(
                FacetEvidenceCoverage(
                    facet_index=facet_index,
                    status="conflicting",
                    selected_chunk_ids=tuple(c.chunk_id for c in facet_selected),
                    conflict_groups=assessments[facet_index].conflict_groups,
                    reason="assessment_conflict",
                )
            )
        elif facet_index in conflict_budget_exhausted:
            coverage.append(
                FacetEvidenceCoverage(
                    facet_index=facet_index,
                    status="unresolved",
                    reason="budget_exhausted",
                )
            )
        elif facet_selected:
            coverage.append(
                FacetEvidenceCoverage(
                    facet_index=facet_index,
                    status="covered",
                    selected_chunk_ids=tuple(c.chunk_id for c in facet_selected),
                    reason=(
                        "assessment_unavailable"
                        if facet_index in assessment_unavailable
                        else ""
                    ),
                )
            )
        elif facet_index in supported:
            coverage.append(
                FacetEvidenceCoverage(
                    facet_index=facet_index,
                    status="unresolved",
                    reason="budget_exhausted",
                )
            )
        else:
            coverage.append(
                FacetEvidenceCoverage(
                    facet_index=facet_index,
                    status="unresolved",
                    reason=(
                        "assessment_unavailable"
                        if facet_index in assessment_unavailable
                        else "no_supporting_evidence"
                    ),
                )
            )

    return selected, EvidenceSelectionPlan(
        query_plan=evidence_plan,
        coverage=tuple(coverage),
    )
