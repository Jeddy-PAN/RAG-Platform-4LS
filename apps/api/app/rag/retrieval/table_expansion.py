"""Table-aware retrieval: intent detection, scoring, expansion, dedup, budget.

Handles project-mode queries where the system automatically identifies
the target document and table without requiring a frontend file selector.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.rag.retrieval.types import (
    RetrievalCandidate,
    TableContextCoverage,
    TableSelectionCandidate,
    TableSelectionOutcome,
)


# ── Intent detection ──────────────────────────────────────────────

# Action verbs that indicate listing/showing intent.
_LIST_ACTIONS_CN = [
    "列出", "罗列", "显示", "展示",
]
_LIST_ACTIONS_EN = [
    r"\blist\b", r"\bshow\b", r"\bdisplay\b", r"\benumerate\b",
]

# Objects that explicitly refer to tables / rows / records.
_TABLE_OBJECTS_CN = [
    "表格", "数据表", "配置表", "记录表", "记录", "条目",
    "表格内容", "数据行", "每一行",
]
_TABLE_OBJECT_PATTERNS_CN = [
    r"(?:所有行|全部行|各行)(?!为)",
]
_TABLE_OBJECTS_EN = [
    r"\btable\b", r"\brow\b", r"\brecords?\b", r"\bentries?\b",
    r"\ball\s+rows\b", r"\bevery\s+row\b",
]

# Domain-specific list phrases (noun phrases that imply tabular data).
_DOMAIN_LIST_CN = [
    "server列表", "服务器列表", "账号列表", "节点列表",
    "主机列表", "服务列表", "配置表", "记录列表",
]
_DOMAIN_LIST_EN = [
    r"\bserver\s+list\b", r"\blist\s+of\s+servers\b",
    r"\bhost\s+list\b", r"\baccount\s+list\b",
]

# Full table request patterns: action + table object together.
_FULL_TABLE_PATTERNS_CN = [
    r"列出.*(?:表格|数据表|配置表|记录表)",
    r"罗列.*(?:表格|数据表|配置表|记录表)",
    r"显示.*(?:表格|数据表|配置表|记录表)",
    r"表格.*(?:列出|全部)",
    r"列出.*记录",
    r"(?:列出|罗列|显示|展示).*(?:数据行|每一行|所有行(?!为)|全部行(?!为)|各行(?!为))",
    r"完整表格",
    r"表格内容",
    r"逐行",
    r"全部记录",
    r"所有记录",
]
# Note: standalone "列出全部" / "罗列全部" removed — too general.
# Those only trigger when paired with a table_object or domain_list.
_FULL_TABLE_PATTERNS_EN = [
    r"\blist\s+(all\s+)?(the\s+)?(servers?|rows?|records?|entries?|tables?)\b",
    r"\bshow\s+(all\s+)?(the\s+)?(rows?|tables?|records?)\b",
    r"\bshow\s+the\s+(full\s+)?table\b",
    r"\bcomplete\s+table\b",
    r"\btable\s+contents?\b",
    r"\bevery\s+(row|record|entry)\b",
    r"\ball\s+(rows|records|entries)\b",
]

# Single-row attribute lookup patterns (table-related but not full-table).
_SINGLE_ROW_EN = [
    r"\bwhat\s+is\s+the\b",
    r"\bfind\s+the\b",
    r"\blookup\b",
    r"\bproperties?\s+of\b",
    r"\bdetails?\s+(of|for)\b",
    r"\battributes?\s+of\b",
]


def detect_table_intent(query: str) -> tuple[bool, bool]:
    """Return ``(is_table_query, is_full_table_query)``.

    *is_table_query* is True when the query appears to involve a table.

    *is_full_table_query* requires a compound signal — an action word
    paired with a table object, a domain-specific list phrase, or an
    explicit full-table pattern.  Standalone general words like "列出",
    "全部", or "有哪些" do NOT trigger full-table intent on their own.
    """
    lowered = query.casefold()

    # ── Domain-specific list phrases (strongest signal) ──
    for phrase in _DOMAIN_LIST_CN:
        if phrase in query:
            return True, True
    for pattern in _DOMAIN_LIST_EN:
        if re.search(pattern, lowered):
            return True, True

    # ── Explicit full-table patterns ──
    for pattern in _FULL_TABLE_PATTERNS_CN:
        if re.search(pattern, query):
            return True, True
    for pattern in _FULL_TABLE_PATTERNS_EN:
        if re.search(pattern, lowered):
            return True, True

    # ── Compound signal: action + table object ──
    has_action_cn = any(a in query for a in _LIST_ACTIONS_CN)
    has_action_en = any(re.search(p, lowered) for p in _LIST_ACTIONS_EN)
    has_table_obj_cn = any(o in query for o in _TABLE_OBJECTS_CN) or any(
        re.search(pattern, query) for pattern in _TABLE_OBJECT_PATTERNS_CN
    )
    has_table_obj_en = any(re.search(p, lowered) for p in _TABLE_OBJECTS_EN)

    has_action = has_action_cn or has_action_en
    has_table_obj = has_table_obj_cn or has_table_obj_en

    if has_action and has_table_obj:
        return True, True

    # ── Action + domain noun (server, host, etc.) ──
    _domain_nouns_cn = ["服务器", "主机", "账号", "节点", "实例"]
    _domain_nouns_en = [
        "server", "host", "account", "node", "instance", "record", "entry",
    ]
    has_domain_cn = any(n in query for n in _domain_nouns_cn)
    # Use custom boundary for mixed Chinese+ASCII queries where \b doesn't work
    has_domain_en = any(
        re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", lowered)
        for n in _domain_nouns_en
    )
    if has_action and (has_domain_cn or has_domain_en):
        return True, True

    # ── Single-row attribute lookup (narrow intent) ──
    for pattern in _SINGLE_ROW_EN:
        if re.search(pattern, lowered):
            return True, False

    return False, False


# ── Table identity and scoring ────────────────────────────────────


# Context budget in approximate word tokens.
DEFAULT_TABLE_CONTEXT_BUDGET = 1500


def _normalise_filename(name: str) -> str:
    """Normalise a filename for case-insensitive token matching.

    Strips the extension and replaces ``_``, ``-``, and spaces with a
    single space so ``ASI_Production_Login.docx`` matches
    ``ASI Production Login``.
    """
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return re.sub(r"[_\-\s]+", " ", stem).strip().casefold()


def _normalise_match_text(value: str) -> str:
    """Normalize separators and camel case before semantic token matching."""

    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return re.sub(r"[_\-\s]+", " ", separated).strip().casefold()


def _match_tokens(value: str) -> set[str]:
    """Extract ASCII and CJK tokens without merging mixed-language phrases."""

    return set(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", _normalise_match_text(value)))


def _is_domain_list_query(query: str) -> bool:
    """Return whether the query uses a known domain-specific list phrase."""

    lowered = query.casefold()
    return any(phrase in query for phrase in _DOMAIN_LIST_CN) or any(
        re.search(pattern, lowered) for pattern in _DOMAIN_LIST_EN
    )


def _header_match_score(query: str, header: str) -> float:
    """Match headers by phrase, token, prefix, and common domain concepts."""

    normalized_query = _normalise_match_text(query)
    normalized_header = _normalise_match_text(header)
    if normalized_header and normalized_header in normalized_query:
        return 1.0

    query_tokens = _match_tokens(query)
    header_tokens = _match_tokens(header)
    for query_token in query_tokens:
        for header_token in header_tokens:
            if len(query_token) >= 3 and len(header_token) >= 3:
                if query_token == header_token:
                    return 1.0
                if query_token.startswith(header_token) or header_token.startswith(query_token):
                    return 0.9

    concept_aliases = (
        ("server", "服务器", "主机"),
        ("host", "主机"),
        ("account", "账号"),
        ("username", "user name", "用户名", "用户"),
        ("password", "密码"),
        ("service", "服务"),
        ("node", "节点"),
        ("instance", "实例"),
    )
    compact_query = normalized_query.replace(" ", "")
    compact_header = normalized_header.replace(" ", "")
    for aliases in concept_aliases:
        if any(alias.replace(" ", "") in compact_query for alias in aliases) and any(
            alias.replace(" ", "") in compact_header for alias in aliases
        ):
            return 0.8
    return 0.0


def _candidate_relevance(candidate: RetrievalCandidate) -> float:
    """Return a comparable 0..1 relevance signal across retrieval modes."""

    metadata = candidate.score_metadata or {}
    vector_relevance = (
        max(0.0, min(float(candidate.vector_score), 1.0))
        if candidate.vector_score is not None
        else 0.0
    )
    keyword_relevance = (
        1.0 - 1.0 / (1.0 + max(float(candidate.keyword_score), 0.0))
        if candidate.keyword_score is not None
        else 0.0
    )
    absolute_relevance = max(vector_relevance, keyword_relevance)
    if candidate.fused_score is not None and (
        metadata.get("fusion_method") == "weighted_rrf"
        or "vector_rrf_score" in metadata
        or "keyword_rrf_score" in metadata
    ):
        fused_relevance = max(0.0, min(float(candidate.fused_score), 1.0))
        return max(absolute_relevance, min(fused_relevance, absolute_relevance + 0.2))
    if candidate.vector_score is not None:
        return vector_relevance
    if candidate.keyword_score is not None:
        return keyword_relevance
    if candidate.fused_score is not None:
        return max(0.0, min(float(candidate.fused_score), 1.0))
    return 0.0


def _score_table_group(
    query: str,
    doc_id: uuid.UUID,
    doc_name: str,
    table_index: int,
    candidates: list[RetrievalCandidate],
) -> tuple[float, dict]:
    """Score a (document_id, table_index) group against the query."""
    lowered = _normalise_match_text(query)
    norm_name = _normalise_filename(doc_name)
    breakdown: dict = {}

    # 1. Filename match — highest weight
    name_tokens = set(norm_name.split())
    query_tokens = _match_tokens(query)
    name_overlap = name_tokens & query_tokens
    # Also check if the full normalised name appears as a phrase
    filename_hit = norm_name in lowered
    if filename_hit:
        score_name = 1.0
    elif name_overlap:
        score_name = len(name_overlap) / max(len(name_tokens), 1) * 0.8
    else:
        score_name = 0.0
    breakdown["filename"] = score_name

    # 2. Caption match
    caption_scores = []
    for c in candidates:
        caption = (c.source_metadata or {}).get("caption")
        normalized_caption = _normalise_match_text(caption) if caption else ""
        if normalized_caption and normalized_caption in lowered:
            caption_scores.append(1.0)
        elif caption and any(
            token in normalized_caption for token in query_tokens if len(token) > 2
        ):
            caption_scores.append(0.5)
    score_caption = max(caption_scores) if caption_scores else 0.0
    breakdown["caption"] = score_caption

    # 3. Header match
    header_scores = []
    for c in candidates:
        headers = (c.source_metadata or {}).get("headers") or []
        for h in headers:
            if h:
                header_scores.append(_header_match_score(query, h))
    score_headers = max(header_scores) if header_scores else 0.0
    breakdown["headers"] = score_headers

    # 4. Strongest retrieval evidence for this table, normalized to 0..1.
    score_retrieval = max((_candidate_relevance(c) for c in candidates), default=0.0)
    breakdown["retrieval"] = round(score_retrieval, 3)

    # 5. Explicit list intent is useful evidence, but cannot pass the
    # threshold by itself when retrieval and table identity are unrelated.
    _, is_full_table_query = detect_table_intent(query)
    if _is_domain_list_query(query):
        score_intent = 1.0
    elif is_full_table_query:
        score_intent = 0.5
    else:
        score_intent = 0.0
    breakdown["list_intent"] = score_intent

    # Weighted combination
    total = (
        score_name * 3.0 +
        score_caption * 2.0 +
        score_headers * 2.0 +
        score_retrieval * 2.0 +
        score_intent * 1.0
    ) / 10.0
    return round(total, 4), breakdown


def _aggregate_candidates_by_table(
    candidates: list[RetrievalCandidate],
) -> dict[tuple[uuid.UUID, int], list[RetrievalCandidate]]:
    """Group candidates by (document_id, table_index)."""
    groups: dict[tuple[uuid.UUID, int], list[RetrievalCandidate]] = {}
    for c in candidates:
        meta = c.source_metadata or {}
        t_idx = meta.get("table_index")
        if t_idx is None:
            continue
        key = (c.document_id, t_idx)
        groups.setdefault(key, []).append(c)
    return groups


# Absolute minimum score to accept a table selection.  Below this the
# candidate pool does not contain enough evidence that the query is
# actually about the table — avoid hijacking ordinary paragraph queries.
_MIN_TABLE_SCORE = 0.15


def select_target_table(
    query: str,
    candidates: list[RetrievalCandidate],
    min_score_gap: float = 0.15,
) -> TableSelectionOutcome:
    """Select the best-matching table from a wide candidate pool.

    Returns ``TableSelectionOutcome`` with:
    - ``selected`` when one table clearly wins
    - ``ambiguous`` when the top two are too close
    - ``insufficient_score`` when the best score is too low
    - ``none`` when no table candidates exist
    """
    groups = _aggregate_candidates_by_table(candidates)
    if not groups:
        return TableSelectionOutcome(status="none", reason="no table candidates in pool")

    scored: list[TableSelectionCandidate] = []
    for (doc_id, t_idx), group in groups.items():
        doc_name = group[0].document_name or "unknown"
        score, breakdown = _score_table_group(query, doc_id, doc_name, t_idx, group)
        caption = next(
            (
                (candidate.source_metadata or {}).get("caption")
                for candidate in group
                if (candidate.source_metadata or {}).get("caption")
            ),
            None,
        )
        scored.append(
            TableSelectionCandidate(
                document_id=doc_id,
                document_name=doc_name,
                table_index=t_idx,
                caption=caption,
                score=score,
                score_breakdown=breakdown,
            )
        )

    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    candidates_out = scored[:4]
    best = scored[0]

    # Absolute minimum score — avoid hijacking ordinary queries
    if best.score < _MIN_TABLE_SCORE:
        return TableSelectionOutcome(
            status="insufficient_score",
            candidates=candidates_out,
            reason=f"best score {best.score:.3f} below minimum {_MIN_TABLE_SCORE}",
        )

    if len(scored) > 1:
        second_score = scored[1].score
        gap = best.score - second_score
        if gap < min_score_gap:
            return TableSelectionOutcome(
                status="ambiguous",
                candidates=candidates_out,
                reason=f"top candidates too close (gap={gap:.3f} < {min_score_gap})",
            )

    return TableSelectionOutcome(
        status="selected",
        selected=best,
        candidates=candidates_out,
        reason="selected by scoring",
    )


# ── Expansion and dedup ───────────────────────────────────────────


def expand_same_table(
    db: Session,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    table_index: int,
) -> list[RetrievalCandidate]:
    """Load all active chunks for a table, sorted by coverage priority."""
    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.project_id == project_id,
            Chunk.document_id == document_id,
            Chunk.is_active == True,
        )
    ).all()

    table_chunks: list[RetrievalCandidate] = []
    row_chunks: list[RetrievalCandidate] = []
    other: list[RetrievalCandidate] = []

    for chunk, document in rows:
        meta = chunk.source_metadata or {}
        if meta.get("table_index") != table_index:
            continue

        candidate = RetrievalCandidate(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=document.filename,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            source_metadata=chunk.source_metadata,
        )
        ct = meta.get("table_chunk_type", "")
        if ct in ("table", "table_group"):
            table_chunks.append(candidate)
        elif ct == "table_row":
            row_chunks.append(candidate)
        else:
            other.append(candidate)

    table_chunks.sort(key=lambda c: (c.source_metadata or {}).get("data_row_start", 0))
    row_chunks.sort(key=lambda c: (c.source_metadata or {}).get("data_row", 0))
    return table_chunks + other + row_chunks


def dedup_parent_child(chunks: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """Remove headers and child rows already represented by parent chunks."""
    covered: list[tuple[uuid.UUID, int, int, int]] = []
    parent_tables: set[tuple[uuid.UUID, int]] = set()
    parents: list[RetrievalCandidate] = []
    others: list[RetrievalCandidate] = []

    for c in chunks:
        meta = c.source_metadata or {}
        ct = meta.get("table_chunk_type", "")
        if ct in ("table", "table_group"):
            parents.append(c)
            table_index = meta.get("table_index")
            if c.document_id and table_index is not None:
                parent_tables.add((c.document_id, table_index))
            rs = meta.get("data_row_start")
            re = meta.get("data_row_end")
            if c.document_id and table_index is not None and rs and re:
                covered.append((c.document_id, table_index, rs, re))
        else:
            others.append(c)

    kept = list(parents)
    for c in others:
        meta = c.source_metadata or {}
        table_index = meta.get("table_index")
        if (
            meta.get("table_chunk_type") == "table_header"
            and c.document_id
            and table_index is not None
            and (c.document_id, table_index) in parent_tables
        ):
            continue
        if meta.get("table_chunk_type") == "table_row":
            d_row = meta.get("data_row")
            if d_row is not None and c.document_id and table_index is not None:
                if any(
                    cd == c.document_id and ct == table_index and crs <= d_row <= cre
                    for cd, ct, crs, cre in covered
                ):
                    continue
        kept.append(c)

    for i, c in enumerate(kept, start=1):
        c.rank = i
    return kept


# ── Context budget ────────────────────────────────────────────────


def apply_context_budget(
    chunks: list[RetrievalCandidate],
    token_budget: int = DEFAULT_TABLE_CONTEXT_BUDGET,
) -> tuple[list[RetrievalCandidate], bool]:
    """Trim chunks to fit within *token_budget* approximate word tokens.

    All chunk types count toward the budget.  Table/group chunks are
    prioritised: they are added first until the budget is exhausted,
    then row chunks, then non-table chunks.  Returns ``(kept, is_partial)``.
    When *is_partial* is True the caller must not claim completeness.
    """
    # Separate by priority
    table_chunks: list[RetrievalCandidate] = []
    header_chunks: list[RetrievalCandidate] = []
    row_chunks: list[RetrievalCandidate] = []
    other_chunks: list[RetrievalCandidate] = []

    for c in chunks:
        ct = (c.source_metadata or {}).get("table_chunk_type", "")
        if ct in ("table", "table_group"):
            table_chunks.append(c)
        elif ct == "table_header":
            header_chunks.append(c)
        elif ct == "table_row":
            row_chunks.append(c)
        else:
            other_chunks.append(c)

    used = 0
    kept: list[RetrievalCandidate] = []
    overflow: list[RetrievalCandidate] = []

    def _try_add(c: RetrievalCandidate) -> None:
        nonlocal used
        words = len(c.text.split()) if c.text else 0
        if used + words <= token_budget:
            kept.append(c)
            used += words
        else:
            overflow.append(c)

    # Priority order: table/group > header > row > other
    for c in table_chunks:
        _try_add(c)
    for c in header_chunks:
        _try_add(c)
    for c in row_chunks:
        _try_add(c)
    for c in other_chunks:
        _try_add(c)

    is_partial = len(overflow) > 0
    for i, c in enumerate(kept, start=1):
        c.rank = i
    return kept, is_partial


def summarize_table_context(
    chunks: list[RetrievalCandidate],
    selected: TableSelectionCandidate,
) -> TableContextCoverage:
    """Summarize the selected table rows represented by kept chunks."""

    ranges: list[tuple[int, int]] = []
    total_rows: int | None = None
    for chunk in chunks:
        metadata = chunk.source_metadata or {}
        if (
            chunk.document_id != selected.document_id
            or metadata.get("table_index") != selected.table_index
        ):
            continue

        metadata_total = metadata.get("total_rows") or metadata.get("row_count")
        if isinstance(metadata_total, int) and metadata_total > 0:
            total_rows = max(total_rows or 0, metadata_total)

        row_start = metadata.get("data_row_start")
        row_end = metadata.get("data_row_end")
        if isinstance(row_start, int) and isinstance(row_end, int) and row_start > 0:
            ranges.append((row_start, row_end))
            continue

        data_row = metadata.get("data_row")
        if isinstance(data_row, int) and data_row > 0:
            ranges.append((data_row, data_row))

    merged_ranges: list[tuple[int, int]] = []
    for row_start, row_end in sorted(ranges):
        if not merged_ranges or row_start > merged_ranges[-1][1] + 1:
            merged_ranges.append((row_start, row_end))
        else:
            previous_start, previous_end = merged_ranges[-1]
            merged_ranges[-1] = (previous_start, max(previous_end, row_end))

    return TableContextCoverage(
        document_id=selected.document_id,
        document_name=selected.document_name,
        table_index=selected.table_index,
        row_ranges=merged_ranges,
        total_rows=total_rows,
    )
