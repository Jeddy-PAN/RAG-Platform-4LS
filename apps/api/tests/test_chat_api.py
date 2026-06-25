import uuid

from app.models.conversation import Conversation, Message, MessageCitation
from app.models.retrieval import RetrievalLog
from app.rag.providers.chat import ChatProviderResult
from tests.retrieval_test_helpers import seed_retrieval_chunk


class FakeChatProvider:
    def generate_chat_completion(self, messages, temperature=0.1):
        return ChatProviderResult(content="Escalation starts after triage.", model="fake-chat")


def test_chat_api_creates_conversation_messages_and_citations(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Chat API should persist conversation, messages, citations, and retrieval log."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "chat",
            "Escalation starts after triage.",
            [0.1] * 1024,
        )
        db.commit()
        project_id = project.id

    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: FakeChatProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": None,
            "message": "What is escalation?",
            "retrieval": {"mode": "hybrid", "top_k": 3},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Escalation starts after triage."
    assert body["citations"]
    assert body["retrieval_log_id"]
    assert body["model"] == "fake-chat"

    with sqlite_session_factory() as db:
        assert db.query(Conversation).count() == 1
        assert db.query(Message).count() == 2
        assert db.query(MessageCitation).count() == 1
        assert db.query(RetrievalLog).count() == 1


def test_chat_api_returns_refusal_without_retrieved_context(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Chat API should store a grounded refusal when retrieval has no chunks."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "empty-chat", "unrelated", [0.1] * 1024)
        db.commit()
        project_id = project.id

    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: (_ for _ in ()).throw(AssertionError("provider should not be called")),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": None,
            "message": "missing topic",
            "retrieval": {"mode": "keyword", "top_k": 3},
        },
    )

    assert response.status_code == 200
    assert "cannot answer" in response.json()["answer"].lower()


def test_chat_api_rejects_cross_project_conversation(
    api_client,
    sqlite_session_factory,
) -> None:
    """A project cannot continue another project's conversation."""

    with sqlite_session_factory() as db:
        project_a, _, _ = seed_retrieval_chunk(db, "chat-a", "alpha", [0.1] * 1024)
        project_b, _, _ = seed_retrieval_chunk(db, "chat-b", "beta", [0.1] * 1024)
        conversation = Conversation(project_id=project_b.id)
        db.add(conversation)
        db.commit()
        project_a_id = project_a.id
        conversation_id = conversation.id

    response = api_client.post(
        f"/api/projects/{project_a_id}/chat/messages",
        json={
            "conversation_id": str(conversation_id),
            "message": "What is beta?",
            "retrieval": {"mode": "keyword", "top_k": 3},
        },
    )

    assert response.status_code == 404


def test_conversation_api_lists_gets_and_deletes_project_conversation(
    api_client,
    sqlite_session_factory,
) -> None:
    """Conversation endpoints should manage project-scoped chat history."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "conversation", "alpha", [0.1] * 1024)
        conversation = Conversation(project_id=project.id, title="Thread")
        db.add(conversation)
        db.flush()
        message = Message(
            project_id=project.id,
            conversation_id=conversation.id,
            role="assistant",
            content="Answer",
        )
        db.add(message)
        db.commit()
        project_id = project.id
        conversation_id = conversation.id

    list_response = api_client.get(f"/api/projects/{project_id}/conversations")
    get_response = api_client.get(
        f"/api/projects/{project_id}/conversations/{conversation_id}"
    )
    delete_response = api_client.delete(
        f"/api/projects/{project_id}/conversations/{conversation_id}"
    )
    missing_response = api_client.get(
        f"/api/projects/{project_id}/conversations/{conversation_id}"
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == str(conversation_id)
    assert get_response.status_code == 200
    assert get_response.json()["messages"][0]["content"] == "Answer"
    assert delete_response.status_code == 204
    assert missing_response.status_code == 404
