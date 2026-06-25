import uuid

from app.rag.prompting import build_chat_prompt
from app.rag.retrieval.types import RetrievalCandidate


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
