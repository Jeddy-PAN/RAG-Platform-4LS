import uuid

import pytest

from app.rag.retrieval.table_expansion import (
    apply_context_budget,
    dedup_parent_child,
    detect_table_intent,
    select_target_table,
    summarize_table_context,
)
from app.rag.retrieval.types import RetrievalCandidate


def _table_candidate(
    document_name: str,
    *,
    document_id: uuid.UUID | None = None,
    table_index: int = 0,
    vector_score: float = 0.8,
    headers: list[str] | None = None,
    row_start: int = 1,
    row_end: int = 8,
    total_rows: int = 8,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        document_name=document_name,
        chunk_index=0,
        text="ServerName | Host | User",
        source_metadata={
            "table_index": table_index,
            "table_chunk_type": "table_group",
            "headers": headers or ["ServerName", "Host", "User"],
            "data_row_start": row_start,
            "data_row_end": row_end,
            "total_rows": total_rows,
        },
        vector_score=vector_score,
        fused_score=vector_score,
    )


def _candidate_with_metadata(
    document_id: uuid.UUID,
    table_index: int,
    chunk_type: str,
    **metadata,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_name="tables.docx",
        chunk_index=0,
        text=f"{chunk_type} content",
        source_metadata={
            "table_index": table_index,
            "table_chunk_type": chunk_type,
            **metadata,
        },
    )


@pytest.mark.parametrize(
    "query",
    [
        "列出代表性案例",
        "显示表达式",
        "显示所有安全要求",
        "列出所有行为规范",
    ],
)
def test_general_chinese_queries_do_not_trigger_table_intent(query: str) -> None:
    """Single characters inside ordinary words must not look like table objects."""

    assert detect_table_intent(query) == (False, False)


@pytest.mark.parametrize(
    "query",
    [
        "罗列这个表格的全部内容",
        "列出所有行",
        "显示配置表",
    ],
)
def test_explicit_chinese_table_queries_still_trigger_full_table_intent(query: str) -> None:
    """Tightening Chinese matching must preserve explicit table requests."""

    assert detect_table_intent(query) == (True, True)


def test_server_list_selects_table_by_header_and_retrieval() -> None:
    """Mixed-language domain list queries should match camel-case headers."""

    candidate = _table_candidate("ASI Production Login.docx")

    outcome = select_target_table("server列表", [candidate])

    assert outcome.status == "selected"
    assert outcome.selected is not None
    assert outcome.selected.document_id == candidate.document_id
    assert outcome.selected.score_breakdown["headers"] >= 0.8


def test_generic_row_list_selects_one_strongly_retrieved_table() -> None:
    """Strong retrieval evidence can select a sole table without its filename."""

    candidate = _table_candidate("inventory.docx", vector_score=1.0, headers=["Name"])

    outcome = select_target_table("list all rows", [candidate])

    assert outcome.status == "selected"


def test_generic_row_list_rejects_a_weakly_related_table() -> None:
    """List intent alone must not let an unrelated sole table hijack retrieval."""

    candidate = _table_candidate("inventory.docx", vector_score=0.1, headers=["Name"])

    outcome = select_target_table("list all rows", [candidate])

    assert outcome.status == "insufficient_score"


def test_generic_row_list_rejects_weak_hybrid_score_normalized_to_one() -> None:
    """Relative hybrid rank must not erase weak absolute retrieval evidence."""

    candidate = _table_candidate("inventory.docx", vector_score=0.1, headers=["Name"])
    candidate.fused_score = 1.0
    candidate.score_metadata = {
        "normalized_vector_score": 1.0,
        "normalized_keyword_score": 1.0,
    }

    outcome = select_target_table("list all rows", [candidate])

    assert outcome.status == "insufficient_score"


@pytest.mark.parametrize(
    "query",
    [
        "列出 ASI Production Login 的表格内容",
        "列出 ASI_Production_Login 的表格内容",
        "列出 asi-production-login.docx 的表格内容",
    ],
)
def test_query_filename_uses_same_normalization_as_document_name(query: str) -> None:
    """Spaces, separators, case, and an optional extension should match equally."""

    candidate = _table_candidate(
        "ASI Production Login.docx",
        vector_score=0.0,
        headers=["Unrelated"],
    )

    outcome = select_target_table(query, [candidate])

    assert outcome.status == "selected"
    assert outcome.selected is not None
    assert outcome.selected.score_breakdown["filename"] == 1.0


def test_ambiguous_selection_includes_top_candidate() -> None:
    """Clarification candidates must include both the first and second table."""

    first = _table_candidate("production.docx")
    second = _table_candidate("staging.docx")

    outcome = select_target_table("server列表", [first, second])

    assert outcome.status == "ambiguous"
    assert [candidate.document_id for candidate in outcome.candidates[:2]] == [
        first.document_id,
        second.document_id,
    ]


def test_table_context_summary_merges_kept_row_ranges() -> None:
    """Prompt coverage should describe only row groups retained by the budget."""

    document_id = uuid.uuid4()
    first = _table_candidate(
        "servers.docx",
        document_id=document_id,
        row_start=1,
        row_end=4,
        total_rows=12,
    )
    second = _table_candidate(
        "servers.docx",
        document_id=document_id,
        row_start=5,
        row_end=8,
        total_rows=12,
    )
    outcome = select_target_table("server列表", [first, second])
    assert outcome.selected is not None

    coverage = summarize_table_context([first, second], outcome.selected)

    assert coverage.row_ranges == [(1, 8)]
    assert coverage.total_rows == 12


def test_dedup_removes_header_and_covered_row_for_same_table_only() -> None:
    """Parent groups repeat headers and rows but must not affect other tables."""

    document_id = uuid.uuid4()
    other_document_id = uuid.uuid4()
    parent = _candidate_with_metadata(
        document_id,
        0,
        "table_group",
        data_row_start=1,
        data_row_end=3,
    )
    duplicate_header = _candidate_with_metadata(document_id, 0, "table_header")
    covered_row = _candidate_with_metadata(document_id, 0, "table_row", data_row=2)
    other_table_header = _candidate_with_metadata(document_id, 1, "table_header")
    other_document_header = _candidate_with_metadata(
        other_document_id,
        0,
        "table_header",
    )

    kept = dedup_parent_child(
        [
            parent,
            duplicate_header,
            covered_row,
            other_table_header,
            other_document_header,
        ]
    )

    assert [candidate.chunk_id for candidate in kept] == [
        parent.chunk_id,
        other_table_header.chunk_id,
        other_document_header.chunk_id,
    ]
    assert [candidate.rank for candidate in kept] == [1, 2, 3]


def test_context_budget_reports_overflow_without_exceeding_limit() -> None:
    """All table groups count toward the independent table context budget."""

    first = _table_candidate("servers.docx", row_start=1, row_end=4)
    second = _table_candidate(
        "servers.docx",
        document_id=first.document_id,
        row_start=5,
        row_end=8,
    )
    first.text = "one two three"
    second.text = "four five six"

    kept, partial = apply_context_budget([first, second], token_budget=4)

    assert kept == [first]
    assert partial is True


def test_selection_returns_none_without_table_candidates() -> None:
    """A full-table request falls back normally when the pool has no table chunks."""

    paragraph = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="handbook.docx",
        chunk_index=0,
        text="Ordinary paragraph content",
        source_metadata={"type": "paragraph"},
        vector_score=0.9,
    )

    outcome = select_target_table("列出所有行", [paragraph])

    assert outcome.status == "none"
