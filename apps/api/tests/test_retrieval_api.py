import uuid

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project


def seed_chunk(sqlite_session_factory, text: str = "alpha escalation policy") -> uuid.UUID:
    """Insert one indexed chunk for API retrieval tests."""

    with sqlite_session_factory() as db:
        project = Project(name=f"Project {uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="source.txt",
            storage_path="/tmp/source.txt",
            file_size_bytes=10,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        db.add(
            Chunk(
                project_id=project.id,
                document_id=document.id,
                chunk_index=0,
                text=text,
                content_hash=str(uuid.uuid4()),
                embedding=[0.1] * 1024,
            )
        )
        db.commit()
        return project.id


def test_retrieval_api_returns_debug_fields(api_client, sqlite_session_factory, monkeypatch):
    """Retrieval API should return scored results and a log id."""

    project_id = seed_chunk(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.OpenAIEmbeddingProvider.from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "hybrid", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "alpha"
    assert body["mode"] == "hybrid"
    assert body["retrieval_log_id"]
    assert body["results"][0].keys() >= {
        "rank",
        "chunk_id",
        "document_id",
        "document_name",
        "chunk_index",
        "text_preview",
        "source_metadata",
        "vector_score",
        "keyword_score",
        "fused_score",
        "score_metadata",
    }


def test_vector_retrieval_embeds_query_once(api_client, sqlite_session_factory, monkeypatch):
    """Vector retrieval should embed the query exactly once."""

    project_id = seed_chunk(sqlite_session_factory)
    calls = []

    class Provider:
        def embed_texts(self, texts):
            calls.append(texts)
            return [[0.1] * 1024]

    monkeypatch.setattr(
        "app.rag.retrieval.service.OpenAIEmbeddingProvider.from_settings",
        lambda: Provider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "vector", "top_k": 3},
    )

    assert response.status_code == 200
    assert calls == [["alpha"]]


def test_keyword_retrieval_does_not_use_embedding_provider(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Keyword-only retrieval should not require embedding provider access."""

    project_id = seed_chunk(sqlite_session_factory)

    def fail_if_called():
        raise AssertionError("embedding provider should not be used")

    monkeypatch.setattr(
        "app.rag.retrieval.service.OpenAIEmbeddingProvider.from_settings",
        fail_if_called,
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "keyword", "top_k": 3},
    )

    assert response.status_code == 200


def test_embedding_provider_failure_returns_503(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Vector retrieval should surface embedding provider failures as 503."""

    from app.rag.providers.embeddings import EmbeddingProviderError

    project_id = seed_chunk(sqlite_session_factory)

    class Provider:
        def embed_texts(self, texts):
            raise EmbeddingProviderError("embedding unavailable")

    monkeypatch.setattr(
        "app.rag.retrieval.service.OpenAIEmbeddingProvider.from_settings",
        lambda: Provider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "vector", "top_k": 3},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "embedding unavailable"


def test_retrieval_api_validates_payload(api_client) -> None:
    """Retrieval API should reject invalid query parameters."""

    project_id = uuid.uuid4()

    empty_query = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": " ", "mode": "keyword"},
    )
    bad_weights = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "alpha",
            "mode": "hybrid",
            "vector_weight": 0,
            "keyword_weight": 0,
        },
    )

    assert empty_query.status_code == 422
    assert bad_weights.status_code == 422


def test_missing_project_returns_404(api_client) -> None:
    """Retrieval should fail clearly for unknown projects."""

    response = api_client.post(
        f"/api/projects/{uuid.uuid4()}/retrieval/query",
        json={"query": "alpha", "mode": "keyword"},
    )

    assert response.status_code == 404
