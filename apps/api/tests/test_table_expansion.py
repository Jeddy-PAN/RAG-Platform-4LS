import uuid

import pytest

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project
from app.rag.retrieval.table_expansion import (
    ExpandedTableGroup,
    apply_context_budget,
    apply_multi_table_context_budget,
    dedup_parent_child,
    detect_table_intent,
    expand_selected_table_groups,
    select_table_facets,
    select_target_table,
    summarize_table_context,
)
from app.rag.retrieval.types import (
    RetrievalCandidate,
    TableFacetOutcome,
    TableQueryFacet,
    TableQueryPlan,
    TableSelectionCandidate,
    TableSelectionPlan,
)


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


def test_selects_one_table_per_facet() -> None:
    first = _table_candidate(
        "alpha-inventory.docx",
        table_index=0,
        vector_score=0.9,
        headers=["ServerName"],
    )
    second = _table_candidate(
        "beta-access.docx",
        table_index=0,
        vector_score=0.9,
        headers=["Column 1", "Column 2"],
    )
    query_plan = TableQueryPlan(
        original_query="compound",
        is_compound=True,
        facets=[
            TableQueryFacet(0, "列出 alpha inventory 的 server列表"),
            TableQueryFacet(1, "列出 beta access table 的所有行"),
        ],
    )

    selection = select_table_facets(
        query_plan,
        {0: [first, second], 1: [first, second]},
    )

    assert [outcome.status for outcome in selection.outcomes] == ["selected", "selected"]
    assert selection.outcomes[0].selected.document_id == first.document_id
    assert selection.outcomes[1].selected.document_id == second.document_id
    assert selection.requires_clarification is False


def test_selection_plan_preserves_unresolved_statuses_in_facet_order() -> None:
    first = _table_candidate("alpha-inventory.docx", headers=["ServerName"])
    second = _table_candidate("beta-inventory.docx", headers=["ServerName"])
    query_plan = TableQueryPlan(
        original_query="compound",
        is_compound=True,
        facets=[
            TableQueryFacet(0, "列出 alpha inventory 的所有行"),
            TableQueryFacet(1, "server列表"),
            TableQueryFacet(2, "列出 missing table 的所有行"),
        ],
    )

    selection = select_table_facets(
        query_plan,
        {0: [first, second], 1: [first, second], 2: []},
    )

    assert [outcome.facet.index for outcome in selection.outcomes] == [0, 1, 2]
    assert [outcome.status for outcome in selection.outcomes] == [
        "selected",
        "ambiguous",
        "none",
    ]
    assert selection.requires_clarification is True
    assert selection.unresolved_facet_indexes == [1, 2]
    assert selection.can_generate is False


def test_selection_plan_can_share_one_selected_table() -> None:
    shared = _table_candidate("shared-inventory.docx", headers=["ServerName"])
    query_plan = TableQueryPlan(
        original_query="compound",
        is_compound=True,
        facets=[
            TableQueryFacet(0, "列出 shared inventory 的 server列表"),
            TableQueryFacet(1, "列出 shared inventory 的所有行"),
        ],
    )

    selection = select_table_facets(query_plan, {0: [shared], 1: [shared]})

    assert selection.can_generate is True
    assert {
        (outcome.selected.document_id, outcome.selected.table_index)
        for outcome in selection.selected_outcomes
        if outcome.selected is not None
    } == {(shared.document_id, 0)}


def test_selection_plan_metadata_contains_diagnostics_without_chunk_text() -> None:
    """Serialized selection diagnostics must never include chunk text or content."""

    first = _table_candidate("alpha-inventory.docx", headers=["ServerName"])
    second = _table_candidate("beta-inventory.docx", headers=["ServerName"])
    query_plan = TableQueryPlan(
        original_query="compound",
        is_compound=True,
        facets=[
            TableQueryFacet(0, "列出 alpha inventory 的所有行"),
            TableQueryFacet(1, "server列表"),
        ],
    )
    selection = select_table_facets(query_plan, {0: [first, second], 1: [first, second]})

    metadata = selection.to_metadata()

    assert set(metadata.keys()) == {
        "original_query",
        "can_generate",
        "requires_clarification",
        "unresolved_facet_indexes",
        "facets",
    }
    facet_metadata = metadata["facets"]
    assert [facet["index"] for facet in facet_metadata] == [0, 1]
    assert [facet["status"] for facet in facet_metadata] == ["selected", "ambiguous"]
    assert facet_metadata[0]["selected"]["document_id"] == str(first.document_id)
    assert facet_metadata[0]["selected"]["score_breakdown"]["filename"] == 1.0
    assert len(facet_metadata[1]["candidates"]) == 2

    stack: list = [metadata]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            assert "text" not in value
            assert "content" not in value
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)


def _seed_expansion_table(
    db,
    project_id: uuid.UUID,
    filename: str,
    chunks: list[tuple[str, int, int]],
) -> uuid.UUID:
    """Seed one indexed table with ``table_group`` chunks of known text."""

    document = Document(
        project_id=project_id,
        filename=filename,
        storage_path=f"/tmp/{filename}",
        file_size_bytes=100,
        status=DocumentStatus.indexed,
    )
    db.add(document)
    db.flush()
    for index, (text, row_start, row_end) in enumerate(chunks):
        db.add(
            Chunk(
                project_id=project_id,
                document_id=document.id,
                chunk_index=index,
                text=text,
                content_hash=str(uuid.uuid4()),
                source_metadata={
                    "type": "table",
                    "table_index": 0,
                    "table_chunk_type": "table_group",
                    "headers": ["ServerName"],
                    "data_row_start": row_start,
                    "data_row_end": row_end,
                    "total_rows": row_end,
                },
            )
        )
    return document.id


def _selected_facet_plan(
    first_id: uuid.UUID,
    first_name: str,
    second_id: uuid.UUID,
    second_name: str,
) -> TableSelectionPlan:
    return TableSelectionPlan(
        original_query="compound",
        outcomes=[
            TableFacetOutcome(
                facet=TableQueryFacet(0, "first facet"),
                status="selected",
                selected=TableSelectionCandidate(
                    document_id=first_id,
                    document_name=first_name,
                    table_index=0,
                    score=1.0,
                ),
            ),
            TableFacetOutcome(
                facet=TableQueryFacet(1, "second facet"),
                status="selected",
                selected=TableSelectionCandidate(
                    document_id=second_id,
                    document_name=second_name,
                    table_index=0,
                    score=1.0,
                ),
            ),
        ],
    )


def test_expand_selected_table_groups_separates_distinct_tables(
    sqlite_session_factory,
) -> None:
    """Distinct selected identities must expand as separate groups in facet order."""

    with sqlite_session_factory() as db:
        project = Project(name=f"distinct-groups-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        first_id = _seed_expansion_table(
            db, project.id, "alpha-inventory.docx", [("one two three", 1, 3)]
        )
        second_id = _seed_expansion_table(
            db, project.id, "beta-access.docx", [("four five six", 1, 3)]
        )
        db.commit()
        project_id = project.id

    selection_plan = _selected_facet_plan(
        first_id, "alpha-inventory.docx", second_id, "beta-access.docx"
    )

    with sqlite_session_factory() as db:
        groups = expand_selected_table_groups(db, project_id, selection_plan)

    assert len(groups) == 2
    assert groups[0].facet_indexes == (0,)
    assert groups[1].facet_indexes == (1,)


def test_expand_selected_table_groups_shares_one_table_across_facets(
    sqlite_session_factory,
) -> None:
    """Two facets selecting the same table must expand it once with both indexes."""

    with sqlite_session_factory() as db:
        project = Project(name=f"shared-group-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        shared_id = _seed_expansion_table(
            db, project.id, "shared-inventory.docx", [("one two three", 1, 3)]
        )
        db.commit()
        project_id = project.id

    shared_plan = TableSelectionPlan(
        original_query="compound",
        outcomes=[
            TableFacetOutcome(
                facet=TableQueryFacet(0, "first facet"),
                status="selected",
                selected=TableSelectionCandidate(
                    document_id=shared_id,
                    document_name="shared-inventory.docx",
                    table_index=0,
                    score=1.0,
                ),
            ),
            TableFacetOutcome(
                facet=TableQueryFacet(1, "second facet"),
                status="selected",
                selected=TableSelectionCandidate(
                    document_id=shared_id,
                    document_name="shared-inventory.docx",
                    table_index=0,
                    score=1.0,
                ),
            ),
        ],
    )

    with sqlite_session_factory() as db:
        shared_groups = expand_selected_table_groups(db, project_id, shared_plan)

    assert len(shared_groups) == 1
    assert shared_groups[0].facet_indexes == (0, 1)
    assert all(
        candidate.score_metadata["table_facet_indexes"] == [0, 1]
        for candidate in shared_groups[0].chunks
    )


def test_multi_table_context_budget_redistributes_unused_quota(
    sqlite_session_factory,
) -> None:
    """Unused quota must flow to a partial table before the final rank assignment."""

    with sqlite_session_factory() as db:
        project = Project(name=f"budget-redistribute-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        first_id = _seed_expansion_table(
            db,
            project.id,
            "alpha-inventory.docx",
            [
                ("one two three four five six", 1, 3),
                ("seven eight", 4, 4),
            ],
        )
        second_id = _seed_expansion_table(
            db,
            project.id,
            "beta-access.docx",
            [
                ("nine ten", 1, 2),
                ("eleven twelve", 3, 4),
            ],
        )
        db.commit()
        project_id = project.id
        first_document_id = first_id
        second_document_id = second_id

    selection_plan = _selected_facet_plan(
        first_id, "alpha-inventory.docx", second_id, "beta-access.docx"
    )

    with sqlite_session_factory() as db:
        groups = expand_selected_table_groups(db, project_id, selection_plan)

    results, contexts, partial = apply_multi_table_context_budget(groups, token_budget=12)

    assert {context.selection.document_id for context in contexts} == {
        first_document_id,
        second_document_id,
    }
    assert sum(len(candidate.text.split()) for candidate in results) <= 12
    assert [candidate.rank for candidate in results] == list(range(1, len(results) + 1))
    assert partial == any(context.is_partial for context in contexts)


def test_multi_table_context_budget_marks_only_truncated_table_partial(
    sqlite_session_factory,
) -> None:
    """Only the table that still overflows its quota may be marked partial."""

    with sqlite_session_factory() as db:
        project = Project(name=f"budget-partial-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        first_id = _seed_expansion_table(
            db,
            project.id,
            "alpha-inventory.docx",
            [
                ("a-one a-two a-three a-four a-five a-six", 1, 3),
                (
                    "a-seven a-eight a-nine a-ten a-eleven a-twelve "
                    "a-thirteen a-fourteen",
                    4,
                    8,
                ),
            ],
        )
        second_id = _seed_expansion_table(
            db,
            project.id,
            "beta-access.docx",
            [("b-one b-two", 1, 2)],
        )
        db.commit()
        project_id = project.id

    selection_plan = _selected_facet_plan(
        first_id, "alpha-inventory.docx", second_id, "beta-access.docx"
    )

    with sqlite_session_factory() as db:
        groups = expand_selected_table_groups(db, project_id, selection_plan)

    results, contexts, partial = apply_multi_table_context_budget(groups, token_budget=12)

    assert partial is True
    assert contexts[0].is_partial is True
    assert contexts[1].is_partial is False
    assert sum(len(candidate.text.split()) for candidate in results) <= 12


def test_multi_table_budget_never_exceeds_global_limit_when_group_keeps_nothing(
    sqlite_session_factory,
) -> None:
    """A group that initially keeps zero words must not double-count its quota."""

    with sqlite_session_factory() as db:
        project = Project(name=f"budget-overflow-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        first_id = _seed_expansion_table(
            db,
            project.id,
            "alpha.docx",
            [("one two three four five six seven eight nine ten", 1, 3)],
        )
        second_id = _seed_expansion_table(
            db,
            project.id,
            "beta.docx",
            [("b-one b-two b-three b-four b-five", 1, 5)],
        )
        db.commit()
        project_id = project.id

    selection_plan = _selected_facet_plan(
        first_id, "alpha.docx", second_id, "beta.docx"
    )

    with sqlite_session_factory() as db:
        groups = expand_selected_table_groups(db, project_id, selection_plan)

    results, contexts, partial = apply_multi_table_context_budget(groups, token_budget=12)

    assert sum(len(candidate.text.split()) for candidate in results) <= 12


def test_multi_table_budget_marks_empty_expansion_partial() -> None:
    """An empty expansion must be explicit partial, never complete coverage."""

    empty_selection = TableSelectionCandidate(
        document_id=uuid.uuid4(),
        document_name="empty.docx",
        table_index=0,
    )
    full_selection = TableSelectionCandidate(
        document_id=uuid.uuid4(),
        document_name="full.docx",
        table_index=0,
    )
    full_chunk = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=full_selection.document_id,
        document_name="full.docx",
        chunk_index=0,
        text="one two three",
        source_metadata={
            "table_index": 0,
            "table_chunk_type": "table_group",
            "data_row_start": 1,
            "data_row_end": 1,
            "total_rows": 1,
        },
    )
    empty_group = ExpandedTableGroup(
        selection=empty_selection,
        facet_indexes=(0,),
        chunks=[],
    )
    full_group = ExpandedTableGroup(
        selection=full_selection,
        facet_indexes=(1,),
        chunks=[full_chunk],
    )

    results, contexts, partial = apply_multi_table_context_budget(
        [empty_group, full_group],
        token_budget=12,
    )

    assert contexts[0].is_partial is True
    assert contexts[1].is_partial is False
    assert partial is True
    assert len(results) == 1
