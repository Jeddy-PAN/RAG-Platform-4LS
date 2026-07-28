import uuid

from app.rag.prompting import build_chat_prompt
from app.rag.retrieval.types import RetrievalCandidate, TableContextCoverage


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
