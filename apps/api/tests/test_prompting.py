import uuid

from app.rag.prompting import build_chat_prompt
from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    EvidenceSelectionPlan,
    FacetEvidenceCoverage,
)
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


def test_prompt_redacts_internal_pdf_geometry_but_keeps_page_provenance() -> None:
    prompt = build_chat_prompt(
        question="What does page two say?",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="runbook.pdf",
                chunk_index=0,
                text="The command result is shown below.",
                source_metadata={
                    "format": "pdf",
                    "page_number": 2,
                    "bbox": [1, 2, 3, 4],
                    "figure_bbox": [5, 6, 7, 8],
                    "figure_index": 0,
                    "extraction_method": "native_text",
                    "extraction_confidence": 1.0,
                },
            )
        ],
        recent_messages=[],
    )

    source_block = prompt.messages[0]["content"]
    assert "page_number" in source_block
    assert "bbox" not in source_block
    assert "figure_" not in source_block
    assert "extraction_" not in source_block
    assert prompt.citation_map[1].source_metadata == {"format": "pdf", "page_number": 2}


def test_prompt_redacts_pdf_inline_header_candidates() -> None:
    prompt = build_chat_prompt(
        question="What rows are present?",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="people.pdf",
                chunk_index=0,
                text="Name | Role\nAlice | Engineer",
                source_metadata={
                    "format": "pdf",
                    "page_number": 1,
                    "headers": [],
                    "header_candidates": ["Name", "Role"],
                    "header_candidate_confidence": 0.6,
                },
            )
        ],
        recent_messages=[],
    )

    source_block = prompt.messages[0]["content"]
    assert "header_candidates" not in source_block
    assert "header_candidate_confidence" not in source_block
    assert prompt.citation_map[1].source_metadata == {
        "format": "pdf",
        "page_number": 1,
        "headers": [],
    }


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


def test_prompt_source_content_uses_original_payload_not_search_text() -> None:
    """The prompt source block carries the payload, never the search labels."""

    chunk_id = uuid.uuid4()
    prompt = build_chat_prompt(
        question="What is in the table?",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=chunk_id,
                document_id=uuid.uuid4(),
                document_name="file.docx",
                chunk_index=0,
                text="alpha payload row",
                search_text=(
                    "Document: file.docx\nTable: Login\nColumns: Server\n"
                    "Content:\nalpha payload row"
                ),
                source_metadata={"page_number": 1},
            )
        ],
        recent_messages=[],
    )

    system = prompt.messages[0]["content"]
    assert "content: alpha payload row" in system
    assert "Document: file.docx" not in system
    assert "Table: Login" not in system
    assert "Columns: Server" not in system
    assert prompt.citation_map[1].text == "alpha payload row"


def _evidence_plan(*queries: str) -> EvidenceQueryPlan:
    return EvidenceQueryPlan(
        original_query="compound fact question",
        facets=tuple(
            EvidenceFacet(index=index, query=query)
            for index, query in enumerate(queries)
        ),
        route="deterministic",
        confidence=0.6,
    )


def _evidence_selection(plan, coverage) -> EvidenceSelectionPlan:
    return EvidenceSelectionPlan(query_plan=plan, coverage=tuple(coverage))


def test_evidence_prompt_maps_facets_to_selected_sources() -> None:
    from app.rag.retrieval.evidence_types import FacetEvidenceCoverage

    first_chunk_id = uuid.uuid4()
    second_chunk_id = uuid.uuid4()
    plan = _evidence_plan("a node-17", "b node-17")
    selection = _evidence_selection(
        plan,
        [
            FacetEvidenceCoverage(
                facet_index=0,
                status="covered",
                selected_chunk_ids=(first_chunk_id,),
            ),
            FacetEvidenceCoverage(
                facet_index=1,
                status="covered",
                selected_chunk_ids=(second_chunk_id,),
            ),
        ],
    )
    prompt = build_chat_prompt(
        "compound fact question",
        [
            RetrievalCandidate(
                chunk_id=first_chunk_id,
                document_id=uuid.uuid4(),
                document_name="a.txt",
                chunk_index=0,
                text="a node-17",
                source_metadata={},
            ),
            RetrievalCandidate(
                chunk_id=second_chunk_id,
                document_id=uuid.uuid4(),
                document_name="b.txt",
                chunk_index=0,
                text="b node-17",
                source_metadata={},
            ),
        ],
        [],
        evidence_selection_plan=selection,
    )

    system = prompt.messages[0]["content"]
    assert "Facet 1 (covered): [Source 1]" in system
    assert "Facet 2 (covered): [Source 2]" in system


def test_evidence_prompt_marks_unresolved_facet() -> None:
    from app.rag.retrieval.evidence_types import FacetEvidenceCoverage

    first_chunk_id = uuid.uuid4()
    plan = _evidence_plan("a node-17", "b node-17")
    selection = _evidence_selection(
        plan,
        [
            FacetEvidenceCoverage(
                facet_index=0,
                status="covered",
                selected_chunk_ids=(first_chunk_id,),
            ),
            FacetEvidenceCoverage(facet_index=1, status="unresolved"),
        ],
    )
    prompt = build_chat_prompt(
        "compound fact question",
        [
            RetrievalCandidate(
                chunk_id=first_chunk_id,
                document_id=uuid.uuid4(),
                document_name="a.txt",
                chunk_index=0,
                text="a node-17",
                source_metadata={},
            )
        ],
        [],
        evidence_selection_plan=selection,
    )

    system = prompt.messages[0]["content"]
    assert "Facet 1 (covered)" in system
    assert "Facet 2 (unresolved)" in system
    assert "not found in the selected knowledge base" in system


def test_evidence_prompt_forbids_budget_limited_conflict_source_for_unresolved_facet() -> None:
    from app.rag.retrieval.evidence_types import FacetEvidenceCoverage

    shared_chunk_id = uuid.uuid4()
    covered_chunk_id = uuid.uuid4()
    plan = _evidence_plan("a node-17", "b node-17")
    selection = _evidence_selection(
        plan,
        [
            FacetEvidenceCoverage(
                facet_index=0,
                status="unresolved",
                selected_chunk_ids=(shared_chunk_id,),
                reason="budget_exhausted",
            ),
            FacetEvidenceCoverage(
                facet_index=1,
                status="covered",
                selected_chunk_ids=(covered_chunk_id,),
            ),
        ],
    )
    prompt = build_chat_prompt(
        "compound fact question",
        [
            RetrievalCandidate(
                chunk_id=shared_chunk_id,
                document_id=uuid.uuid4(),
                document_name="shared.txt",
                chunk_index=0,
                text="a node-17 claim; b node-17 claim",
                source_metadata={},
                score_metadata={"evidence_facet_indexes": [0, 1]},
            ),
            RetrievalCandidate(
                chunk_id=covered_chunk_id,
                document_id=uuid.uuid4(),
                document_name="covered.txt",
                chunk_index=0,
                text="b node-17 confirmed",
                source_metadata={},
                score_metadata={"evidence_facet_indexes": [1]},
            ),
        ],
        [],
        evidence_selection_plan=selection,
    )

    system = prompt.messages[0]["content"]
    assert "Facet 1 (unresolved)" in system
    assert "Do not use or cite any source for this facet" in system
    assert "Facet 2 (covered): [Source 2]" in system


def test_evidence_prompt_all_unresolved_refuses() -> None:
    from app.rag.retrieval.evidence_types import FacetEvidenceCoverage

    plan = _evidence_plan("a node-17", "b node-17")
    selection = _evidence_selection(
        plan,
        [
            FacetEvidenceCoverage(facet_index=0, status="unresolved"),
            FacetEvidenceCoverage(facet_index=1, status="unresolved"),
        ],
    )
    prompt = build_chat_prompt(
        "compound fact question",
        [
            RetrievalCandidate(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="noise.txt",
                chunk_index=0,
                text="unrelated",
                source_metadata={},
            )
        ],
        [],
        evidence_selection_plan=selection,
    )

    assert prompt.should_refuse is True


def test_evidence_prompt_separates_conflict_groups() -> None:
    from app.rag.retrieval.evidence_types import FacetEvidenceCoverage

    first_chunk_id = uuid.uuid4()
    second_chunk_id = uuid.uuid4()
    plan = _evidence_plan("password node-17")
    selection = _evidence_selection(
        plan,
        [
            FacetEvidenceCoverage(
                facet_index=0,
                status="conflicting",
                selected_chunk_ids=(first_chunk_id, second_chunk_id),
                conflict_groups=((first_chunk_id,), (second_chunk_id,)),
            ),
        ],
    )
    prompt = build_chat_prompt(
        "find the password for node-17",
        [
            RetrievalCandidate(
                chunk_id=first_chunk_id,
                document_id=uuid.uuid4(),
                document_name="p1.txt",
                chunk_index=0,
                text="password node-17 alpha",
                source_metadata={},
            ),
            RetrievalCandidate(
                chunk_id=second_chunk_id,
                document_id=uuid.uuid4(),
                document_name="p2.txt",
                chunk_index=0,
                text="password node-17 beta",
                source_metadata={},
            ),
        ],
        [],
        evidence_selection_plan=selection,
    )

    system = prompt.messages[0]["content"]
    assert "conflicting" in system
    assert "[Source 1]" in system
    assert "[Source 2]" in system
    assert "Never merge values or pick a winner" in system
