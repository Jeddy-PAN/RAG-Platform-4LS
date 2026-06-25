import uuid

from app.rag.answering import generate_answer
from app.rag.providers.chat import ChatProviderResult


class FakeChatProvider:
    def __init__(self) -> None:
        self.calls = []

    def generate_chat_completion(self, messages, temperature=0.1):
        self.calls.append(messages)
        return ChatProviderResult(content="Use escalation policy.", model="fake-chat")


def test_generate_answer_refuses_without_chunks() -> None:
    """No retrieved chunks should return a refusal without calling provider."""

    provider = FakeChatProvider()

    result = generate_answer(
        question="What is escalation?",
        retrieved_chunks=[],
        recent_messages=[],
        chat_provider=provider,
    )

    assert "cannot answer" in result.answer.lower()
    assert result.model == "local-refusal"
    assert provider.calls == []


def test_generate_answer_calls_provider_with_context() -> None:
    """Available context should be sent to the chat provider."""

    from app.rag.retrieval.types import RetrievalCandidate

    provider = FakeChatProvider()
    result = generate_answer(
        question="What is escalation?",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="handbook.pdf",
                chunk_index=0,
                text="Escalation policy.",
                source_metadata={},
            )
        ],
        recent_messages=[],
        chat_provider=provider,
    )

    assert result.answer == "Use escalation policy."
    assert result.model == "fake-chat"
    assert provider.calls
