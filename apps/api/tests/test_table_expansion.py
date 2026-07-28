import uuid

from app.rag.retrieval.table_expansion import (
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
