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


def test_generate_answer_passes_plural_table_context(monkeypatch) -> None:
    from app.rag.prompting import ChatPrompt
    from app.rag.retrieval.types import RetrievalCandidate

    captured: dict = {}
    selection_plan = object()
    table_contexts = [object()]

    def fake_build_chat_prompt(*args, **kwargs):
        captured.update(kwargs)
        return ChatPrompt(
            messages=[{"role": "user", "content": "compound"}],
            citation_map={},
            should_refuse=False,
        )

    monkeypatch.setattr("app.rag.answering.build_chat_prompt", fake_build_chat_prompt)
    generate_answer(
        question="compound",
        retrieved_chunks=[
            RetrievalCandidate(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="synthetic.docx",
                chunk_index=0,
                text="synthetic row",
                source_metadata={},
            )
        ],
        recent_messages=[],
        chat_provider=FakeChatProvider(),
        table_selection_plan=selection_plan,
        table_contexts=table_contexts,
    )
    assert captured["table_selection_plan"] is selection_plan
    assert captured["table_contexts"] is table_contexts
