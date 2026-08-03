import uuid

from app.rag.prompting import build_chat_prompt
from app.rag.retrieval.types import (
    FacetTableContextCoverage,
    RetrievalCandidate,
    TableContextCoverage,
    TableFacetOutcome,
    TableQueryFacet,
    TableSelectionCandidate,
    TableSelectionPlan,
)


def test_prompt_includes_source_blocks_and_citation_map() -> None:
    """Retrieved chunks should become explicit source blocks in the prompt."""

    chunk_id = uuid.uuid4()
    document_id = uuid.uuid4()
    prompt = build_chat_prompt(
        question="What is escalation?",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=chunk_id,
                document_id=document_id,
                document_name="handbook.pdf",
                chunk_index=0,
                text="Escalation starts after triage.",
                source_metadata={"page_number": 4},
            )
        ],
        recent_messages=[{"role": "user", "content": "Previous question"}],
    )

    assert "[Source 1]" in prompt.messages[0]["content"]
    assert "Escalation starts after triage." in prompt.messages[0]["content"]
    assert prompt.citation_map[1].chunk_id == chunk_id
    assert prompt.messages[-1] == {"role": "user", "content": "What is escalation?"}


def test_prompt_empty_retrieval_marks_no_answer() -> None:
    """No retrieved chunks should trigger the no-answer path."""

    prompt = build_chat_prompt(
        question="What is escalation?",
        retrieved_chunks=[],
        recent_messages=[],
    )

    assert prompt.should_refuse
    assert prompt.citation_map == {}


def test_partial_table_prompt_forbids_complete_answer_and_names_coverage() -> None:
    """A truncated table must be described as partial in the model instructions."""

    document_id = uuid.uuid4()
    prompt = build_chat_prompt(
        question="List all servers",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=uuid.uuid4(),
                document_id=document_id,
                document_name="servers.docx",
                chunk_index=0,
                text="ServerName | Host\napp-01 | 10.0.0.1",
                source_metadata={
                    "table_index": 0,
                    "data_row_start": 1,
                    "data_row_end": 4,
                    "total_rows": 12,
                },
            )
        ],
        recent_messages=[],
        context_partial=True,
        table_context=TableContextCoverage(
            document_id=document_id,
            document_name="servers.docx",
            table_index=0,
            row_ranges=[(1, 4)],
            total_rows=12,
        ),
    )

    system_message = prompt.messages[0]["content"]
    assert "table context is partial" in system_message
    assert "Do not state or imply" in system_message
    assert "rows 1-4 of 12" in system_message


def test_prompt_groups_sources_by_compound_table_facet() -> None:
    first_document_id = uuid.uuid4()
    second_document_id = uuid.uuid4()
    first_selection = TableSelectionCandidate(
        document_id=first_document_id,
        document_name="alpha-inventory.docx",
        table_index=0,
    )
    second_selection = TableSelectionCandidate(
        document_id=second_document_id,
        document_name="beta-access.docx",
        table_index=0,
    )
    selection_plan = TableSelectionPlan(
        original_query="compound request",
        outcomes=[
            TableFacetOutcome(
                facet=TableQueryFacet(0, "list all alpha inventory rows"),
                status="selected",
                selected=first_selection,
            ),
            TableFacetOutcome(
                facet=TableQueryFacet(1, "list all beta access rows"),
                status="selected",
                selected=second_selection,
            ),
        ],
    )
    first_table_chunk = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=first_document_id,
        document_name="alpha-inventory.docx",
        chunk_index=0,
        text="ServerName\nalpha-01",
        source_metadata={"table_index": 0},
        score_metadata={"table_facet_indexes": [0]},
    )
    second_table_chunk = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=second_document_id,
        document_name="beta-access.docx",
        chunk_index=0,
        text="Label | State\nbeta-01 | active",
        source_metadata={"table_index": 0},
        score_metadata={"table_facet_indexes": [1]},
    )
    first_complete = FacetTableContextCoverage(
        facet_indexes=(0,),
        selection=first_selection,
        coverage=TableContextCoverage(
            document_id=first_document_id,
            document_name="alpha-inventory.docx",
            table_index=0,
            row_ranges=[(1, 1)],
            total_rows=1,
        ),
        is_partial=False,
    )
    second_complete = FacetTableContextCoverage(
        facet_indexes=(1,),
        selection=second_selection,
        coverage=TableContextCoverage(
            document_id=second_document_id,
            document_name="beta-access.docx",
            table_index=0,
            row_ranges=[(1, 1)],
            total_rows=1,
        ),
        is_partial=False,
    )
    prompt = build_chat_prompt(
        question="compound request",
        retrieved_chunks=[first_table_chunk, second_table_chunk],
        recent_messages=[],
        table_selection_plan=selection_plan,
        table_contexts=[first_complete, second_complete],
    )

    system = prompt.messages[0]["content"]
    assert "Facet 1" in system
    assert "Facet 2" in system
    assert "Answer every resolved facet" in system
    assert "[Source 1]" in system
    assert "[Source 2]" in system

    second_partial = FacetTableContextCoverage(
        facet_indexes=(1,),
        selection=second_selection,
        coverage=TableContextCoverage(
            document_id=second_document_id,
            document_name="beta-access.docx",
            table_index=0,
            row_ranges=[(1, 2)],
            total_rows=5,
        ),
        is_partial=True,
    )
    partial_prompt = build_chat_prompt(
        question="compound request",
        retrieved_chunks=[first_table_chunk, second_table_chunk],
        recent_messages=[],
        table_selection_plan=selection_plan,
        table_contexts=[first_complete, second_partial],
    )
    partial_system = partial_prompt.messages[0]["content"]
    assert "Facet 2" in partial_system
    assert "rows 1-2 of 5" in partial_system
    assert "Do not state or imply that the compound answer is complete" in partial_system
    assert "Facet 1 is partial" not in partial_system


def test_compound_prompt_guards_zero_row_partial_coverage() -> None:
    """A partial context with zero retained rows must still emit a guard."""

    first_document_id = uuid.uuid4()
    first_selection = TableSelectionCandidate(
        document_id=first_document_id,
        document_name="alpha.docx",
        table_index=0,
    )
    selection_plan = TableSelectionPlan(
        original_query="compound",
        outcomes=[
            TableFacetOutcome(
                facet=TableQueryFacet(0, "alpha facet"),
                status="selected",
                selected=first_selection,
            ),
        ],
    )
    chunk = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=first_document_id,
        document_name="alpha.docx",
        chunk_index=0,
        text="one",
        source_metadata={"table_index": 0},
        score_metadata={"table_facet_indexes": [0]},
    )
    partial_ctx = FacetTableContextCoverage(
        facet_indexes=(0,),
        selection=first_selection,
        coverage=TableContextCoverage(
            document_id=first_document_id,
            document_name="alpha.docx",
            table_index=0,
            row_ranges=[],
            total_rows=5,
        ),
        is_partial=True,
    )

    prompt = build_chat_prompt(
        question="compound",
        retrieved_chunks=[chunk],
        recent_messages=[],
        table_selection_plan=selection_plan,
        table_contexts=[partial_ctx],
    )
    system = prompt.messages[0]["content"]
    assert "Facet 1 is partial" in system
    assert "no rows were retained" in system
    assert "Do not state or imply that the compound answer is complete" in system


def test_compound_prompt_names_every_partial_shared_facet() -> None:
    """A partial table shared by two facets must identify every affected facet."""

    first_document_id = uuid.uuid4()
    first_selection = TableSelectionCandidate(
        document_id=first_document_id,
        document_name="shared.docx",
        table_index=0,
    )
    selection_plan = TableSelectionPlan(
        original_query="compound",
        outcomes=[
            TableFacetOutcome(
                facet=TableQueryFacet(0, "first facet"),
                status="selected",
                selected=first_selection,
            ),
            TableFacetOutcome(
                facet=TableQueryFacet(1, "second facet"),
                status="selected",
                selected=first_selection,
            ),
        ],
    )
    chunk = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=first_document_id,
        document_name="shared.docx",
        chunk_index=0,
        text="one two",
        source_metadata={"table_index": 0},
        score_metadata={"table_facet_indexes": [0, 1]},
    )
    partial_ctx = FacetTableContextCoverage(
        facet_indexes=(0, 1),
        selection=first_selection,
        coverage=TableContextCoverage(
            document_id=first_document_id,
            document_name="shared.docx",
            table_index=0,
            row_ranges=[(1, 2)],
            total_rows=5,
        ),
        is_partial=True,
    )

    prompt = build_chat_prompt(
        question="compound",
        retrieved_chunks=[chunk],
        recent_messages=[],
        table_selection_plan=selection_plan,
        table_contexts=[partial_ctx],
    )
    system = prompt.messages[0]["content"]
    assert "Facet 1 is partial" in system
    assert "Facet 2 is partial" in system
    assert "Do not state or imply that the compound answer is complete" in system
