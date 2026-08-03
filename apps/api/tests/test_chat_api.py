import json
import time
import uuid

from app.models.chunk import Chunk
from app.models.conversation import Conversation, Message, MessageCitation
from app.models.document import Document, DocumentStatus
from app.models.metrics import ChatRequestMetric
from app.models.project import Project
from app.models.retrieval import RetrievalLog
from app.rag.providers.chat import ChatProviderResult
from tests.retrieval_test_helpers import seed_retrieval_chunk


def _constant_embedding_provider():
    return type(
        "Provider",
        (),
        {
            "embed_texts": lambda self, texts: [
                [0.1] * 1024 for _ in texts
            ]
        },
    )()


def seed_compound_clarification_tables(
    sqlite_session_factory,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed alpha plus two equally-scored access tables for facet clarification."""

    with sqlite_session_factory() as db:
        project = Project(name=f"compound-clarify-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        definitions = (
            ("alpha-inventory.docx", ["ServerName"], ["alpha-01", "alpha-02"]),
            ("beta-access.docx", ["Label", "State"], ["beta-01", "beta-02"]),
            ("gamma-access.docx", ["Label", "State"], ["gamma-01", "gamma-02"]),
        )
        document_ids: list[uuid.UUID] = []
        for filename, headers, values in definitions:
            document = Document(
                project_id=project.id,
                filename=filename,
                storage_path=f"/tmp/{filename}",
                file_size_bytes=100,
                status=DocumentStatus.indexed,
            )
            db.add(document)
            db.flush()
            document_ids.append(document.id)
            parent_text = " | ".join(headers) + "\n" + "\n".join(values)
            db.add(
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=0,
                    text=parent_text,
                    content_hash=str(uuid.uuid4()),
                    embedding=[0.1] * 1024,
                    source_metadata={
                        "type": "table",
                        "table_index": 0,
                        "table_chunk_type": "table_group",
                        "headers": headers,
                        "data_row_start": 1,
                        "data_row_end": 2,
                        "total_rows": 2,
                    },
                )
            )
            for row_number, value in enumerate(values, start=1):
                db.add(
                    Chunk(
                        project_id=project.id,
                        document_id=document.id,
                        chunk_index=row_number,
                        text=f"{headers[0]}: {value}",
                        content_hash=str(uuid.uuid4()),
                        embedding=[0.1] * 1024,
                        source_metadata={
                            "type": "table_row",
                            "table_index": 0,
                            "table_chunk_type": "table_row",
                            "headers": headers,
                            "data_row": row_number,
                            "total_rows": 2,
                        },
                    )
                )
        db.commit()
        return project.id, document_ids[0], document_ids[1], document_ids[2]


class FakeChatProvider:
    def __init__(self) -> None:
        self.calls = []

    def generate_chat_completion(self, messages, temperature=0.1):
        self.calls.append(messages)
        return ChatProviderResult(content="Escalation starts after triage.", model="fake-chat")


def seed_ambiguous_tables(sqlite_session_factory) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Create two equally relevant server tables in one project."""

    with sqlite_session_factory() as db:
        project = Project(name=f"ambiguous-tables-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document_ids: list[uuid.UUID] = []
        for index, filename in enumerate(("production.docx", "staging.docx")):
            document = Document(
                project_id=project.id,
                filename=filename,
                storage_path=f"/tmp/{filename}",
                file_size_bytes=100,
                status=DocumentStatus.indexed,
            )
            db.add(document)
            db.flush()
            document_ids.append(document.id)
            db.add(
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=0,
                    text=f"ServerName | Host\napp-{index + 1} | 10.0.0.{index + 1}",
                    content_hash=str(uuid.uuid4()),
                    embedding=[0.1] * 1024,
                    source_metadata={
                        "type": "table",
                        "table_index": 0,
                        "table_chunk_type": "table",
                        "headers": ["ServerName", "Host"],
                        "data_row_start": 1,
                        "data_row_end": 1,
                        "total_rows": 1,
                    },
                )
            )
        db.commit()
        return project.id, document_ids


def seed_oversized_table(sqlite_session_factory) -> uuid.UUID:
    """Create one table whose row groups cannot both fit the context budget."""

    with sqlite_session_factory() as db:
        project = Project(name=f"oversized-table-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="large-servers.docx",
            storage_path="/tmp/large-servers.docx",
            file_size_bytes=10_000,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        for index, (row_start, row_end) in enumerate(((1, 4), (5, 8))):
            text = "ServerName | Host\n" + " ".join(
                f"server-{index}-{word}" for word in range(800)
            )
            db.add(
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=index,
                    text=text,
                    content_hash=str(uuid.uuid4()),
                    embedding=[0.1] * 1024,
                    source_metadata={
                        "type": "table",
                        "table_index": 0,
                        "table_chunk_type": "table_group",
                        "headers": ["ServerName", "Host"],
                        "data_row_start": row_start,
                        "data_row_end": row_end,
                        "total_rows": 8,
                    },
                )
            )
        db.commit()
        return project.id


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


def test_chat_api_passes_reranker_options_to_retrieval(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Chat retrieval options should enable reranking and persist that choice."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "chat-rerank",
            "google sycamore quantum supremacy",
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
            "message": "What did Google Sycamore claim?",
            "retrieval": {
                "mode": "hybrid",
                "top_k": 3,
                "reranker_enabled": True,
                "reranker_candidate_limit": 10,
            },
        },
    )

    assert response.status_code == 200
    with sqlite_session_factory() as db:
        log = db.query(RetrievalLog).one()
        assert log.retrieval_metadata["reranker_enabled"] is True
        assert log.retrieval_metadata["reranker"] == "keyword_overlap"


def test_chat_metrics_api_records_and_summarizes_chat_requests(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Chat requests should be observable through project-scoped metrics."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "chat-metrics",
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

    chat_response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": None,
            "message": "What is escalation?",
            "retrieval": {"mode": "hybrid", "top_k": 3},
        },
    )
    metrics_response = api_client.get(f"/api/projects/{project_id}/metrics/chat")

    assert chat_response.status_code == 200
    assert metrics_response.status_code == 200
    chat_body = chat_response.json()
    metrics_body = metrics_response.json()
    assert metrics_body["summary"]["request_count"] == 1
    assert metrics_body["summary"]["avg_latency_ms"] >= 0
    assert metrics_body["summary"]["avg_retrieval_latency_ms"] >= 0
    assert metrics_body["summary"]["avg_generation_latency_ms"] >= 0
    assert metrics_body["summary"]["avg_citation_count"] == 1
    assert metrics_body["items"][0]["model"] == "fake-chat"
    assert metrics_body["items"][0]["citation_count"] == 1
    assert metrics_body["items"][0]["retrieval_log_id"] == chat_body["retrieval_log_id"]
    assert metrics_body["items"][0]["conversation_id"] == chat_body["conversation_id"]

    with sqlite_session_factory() as db:
        metric = db.query(ChatRequestMetric).one()
        assert metric.project_id == project_id
        assert metric.citation_count == 1


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


def test_chat_api_clarifies_ambiguous_tables_without_calling_provider(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Ambiguous project tables should return choices instead of an LLM guess."""

    project_id, document_ids = seed_ambiguous_tables(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: (_ for _ in ()).throw(AssertionError("provider should not be called")),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": None,
            "message": "server列表",
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "local-table-clarification"
    assert "production.docx" in body["answer"]
    assert "staging.docx" in body["answer"]
    assert body["citations"] == []

    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(body["assistant_message_id"]))
        candidates = assistant.message_metadata["table_selection"]["candidates"]
        assert {uuid.UUID(candidate["document_id"]) for candidate in candidates} == set(document_ids)
        assert all("score" not in candidate for candidate in candidates)


def test_chat_api_uses_ordinal_reply_to_confirm_ambiguous_table(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """A follow-up ordinal should expand the chosen table without another ambiguity."""

    project_id, document_ids = seed_ambiguous_tables(sqlite_session_factory)
    provider = FakeChatProvider()
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: provider,
    )

    clarification = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={"message": "server列表", "retrieval": {"mode": "hybrid", "top_k": 8}},
    )
    with sqlite_session_factory() as db:
        clarification_message = db.get(
            Message,
            uuid.UUID(clarification.json()["assistant_message_id"]),
        )
        first_candidate_id = clarification_message.message_metadata["table_selection"][
            "candidates"
        ][0]["document_id"]
    confirmation = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": clarification.json()["conversation_id"],
            "message": "第一个",
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )

    assert clarification.status_code == 200
    assert confirmation.status_code == 200
    assert confirmation.json()["model"] == "fake-chat"
    assert len(provider.calls) == 1

    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(confirmation.json()["assistant_message_id"]))
        selected = assistant.message_metadata["table_selection"]["selected"]
        assert selected["document_id"] == first_candidate_id


def test_chat_api_passes_partial_table_coverage_to_prompt_and_metadata(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Budget-truncated tables must constrain generation and expose row coverage."""

    project_id = seed_oversized_table(sqlite_session_factory)
    provider = FakeChatProvider()
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: provider,
    )

    response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={"message": "server列表", "retrieval": {"mode": "hybrid", "top_k": 8}},
    )

    assert response.status_code == 200
    assert len(provider.calls) == 1
    system_message = provider.calls[0][0]["content"]
    assert "table context is partial" in system_message
    assert "rows 1-4 of 8" in system_message

    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(response.json()["assistant_message_id"]))
        assert assistant.message_metadata["context_partial"] is True
        assert assistant.message_metadata["table_context"]["row_ranges"] == [[1, 4]]
        retrieval_log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        assert retrieval_log.retrieval_metadata["context_partial"] is True
        assert retrieval_log.retrieval_metadata["table_context"]["total_rows"] == 8


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


COMPOUND_CLARIFY_QUERY = "列出 Alpha Inventory 表格中的所有 server和列出 access 表格的所有行"


def test_chat_api_compound_clarification_persists_pending_facet(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """An ambiguous compound facet must persist a resumable clarification."""

    project_id, alpha_id, beta_id, gamma_id = seed_compound_clarification_tables(
        sqlite_session_factory
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: _constant_embedding_provider(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: (_ for _ in ()).throw(AssertionError("provider should not be called")),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "message": COMPOUND_CLARIFY_QUERY,
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "local-table-clarification"
    assert body["citations"] == []
    assert "需要确认的子问题" in body["answer"]
    assert "beta-access.docx" in body["answer"]
    assert "gamma-access.docx" in body["answer"]
    assert "alpha-01" not in body["answer"]

    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(body["assistant_message_id"]))
        plan = assistant.message_metadata["table_query_plan"]
        assert plan["status"] == "clarification_required"
        assert plan["original_query"] == COMPOUND_CLARIFY_QUERY
        assert plan["pending_facet_index"] == 1
        assert set(plan["preferred_tables_by_facet"].keys()) == {"0"}
        assert plan["preferred_tables_by_facet"]["0"]["document_id"] == str(alpha_id)
        assert [facet["index"] for facet in plan["selection"]["facets"]] == [0, 1]
        assert {c["document_name"] for c in plan["candidates"]} == {
            "alpha-inventory.docx",
            "beta-access.docx",
            "gamma-access.docx",
        }
        assert "alpha-01" not in json.dumps(plan)
        assert "beta-01" not in json.dumps(plan)


def test_chat_api_compound_confirmation_resumes_original_query(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Confirming the pending facet must rerun the stored query and expand both."""

    project_id, alpha_id, beta_id, gamma_id = seed_compound_clarification_tables(
        sqlite_session_factory
    )
    provider = FakeChatProvider()
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: _constant_embedding_provider(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: provider,
    )

    clarification = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "message": COMPOUND_CLARIFY_QUERY,
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )
    confirmation = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": clarification.json()["conversation_id"],
            "message": "第一个",
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )

    assert clarification.status_code == 200
    assert confirmation.status_code == 200
    assert confirmation.json()["model"] == "fake-chat"
    assert len(provider.calls) == 1
    assert provider.calls[0][-1] == {
        "role": "user",
        "content": COMPOUND_CLARIFY_QUERY,
    }

    with sqlite_session_factory() as db:
        assistant = db.get(
            Message,
            uuid.UUID(confirmation.json()["assistant_message_id"]),
        )
        plan = assistant.message_metadata["table_query_plan"]
        assert plan["status"] == "ready"
        assert len(plan["table_contexts"]) == 2
        assert {context["document_name"] for context in plan["table_contexts"]} == {
            "alpha-inventory.docx",
            "beta-access.docx",
        }


def test_chat_api_compound_sequential_ambiguity(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Two ambiguous facets clarify one at a time and retain earlier picks."""

    project_id, alpha_id, beta_id, gamma_id = seed_compound_clarification_tables(
        sqlite_session_factory
    )
    provider = FakeChatProvider()
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: _constant_embedding_provider(),
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: provider,
    )
    query = "列出 access 表格的所有行和列出 state 表格的所有行"

    first = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={"message": query, "retrieval": {"mode": "hybrid", "top_k": 8}},
    )
    assert first.status_code == 200
    assert first.json()["model"] == "local-table-clarification"
    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(first.json()["assistant_message_id"]))
        plan = assistant.message_metadata["table_query_plan"]
        assert plan["pending_facet_index"] == 0
        assert plan["preferred_tables_by_facet"] == {}

    # SQLite ``now()`` has second precision; space the two clarifications so the
    # latest-assistant lookup cannot tie on identical timestamps.
    time.sleep(1.1)

    second = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": first.json()["conversation_id"],
            "message": "第一个",
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )
    assert second.status_code == 200
    assert second.json()["model"] == "local-table-clarification"
    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(second.json()["assistant_message_id"]))
        plan = assistant.message_metadata["table_query_plan"]
        assert plan["pending_facet_index"] == 1
        assert plan["preferred_tables_by_facet"]["0"]["document_id"] == str(beta_id)

    third = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "conversation_id": second.json()["conversation_id"],
            "message": "第二个",
            "retrieval": {"mode": "hybrid", "top_k": 8},
        },
    )
    assert third.status_code == 200
    assert third.json()["model"] == "fake-chat"
    assert len(provider.calls) == 1
    with sqlite_session_factory() as db:
        assistant = db.get(Message, uuid.UUID(third.json()["assistant_message_id"]))
        plan = assistant.message_metadata["table_query_plan"]
        assert plan["status"] == "ready"
        assert len(plan["table_contexts"]) == 2
        assert {context["document_name"] for context in plan["table_contexts"]} == {
            "beta-access.docx",
            "gamma-access.docx",
        }
