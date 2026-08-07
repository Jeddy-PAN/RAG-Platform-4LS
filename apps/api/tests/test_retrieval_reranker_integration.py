import uuid

from app.core.config import Settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project


def _seed_chunks(sqlite_session_factory, texts: list[str]) -> uuid.UUID:
    with sqlite_session_factory() as db:
        project = Project(name=f"reranker-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="synthetic.txt",
            storage_path="/tmp/synthetic.txt",
            file_size_bytes=100,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        for index, text in enumerate(texts):
            db.add(
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=index,
                    text=text,
                    content_hash=str(uuid.uuid4()),
                )
            )
        db.commit()
        return project.id


def test_service_bounds_rerank_pool_before_final_top_k(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    project_id = _seed_chunks(
        sqlite_session_factory,
        ["node17 lexical first", "node17 semantic second", "node17 tail third"],
    )
    seen: list[list[str]] = []

    class Provider:
        name = "multilingual_cross_encoder"

        def score(self, query, candidates):
            seen.append([candidate.text for candidate in candidates])
            return [0.9 if "semantic" in candidate.text else 0.1 for candidate in candidates]

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(
            reranker_provider="multilingual_cross_encoder",
            reranker_base_url="http://reranker.test",
            reranker_model="synthetic",
            reranker_candidate_limit=2,
        ),
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_reranker_provider_from_settings",
        lambda settings: Provider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "node17",
            "mode": "keyword",
            "top_k": 1,
            "reranker_enabled": True,
            "reranker_candidate_limit": 10,
        },
    )

    assert response.status_code == 200
    assert len(seen) == 1
    assert len(seen[0]) == 2
    assert "tail third" not in seen[0]
    assert response.json()["results"][0]["text_preview"] == "node17 semantic second"
    assert response.json()["results"][0]["score_metadata"]["reranker"] == (
        "multilingual_cross_encoder"
    )


def test_invalid_reranker_configuration_falls_back_without_api_error(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    project_id = _seed_chunks(sqlite_session_factory, ["node17 lexical evidence"])
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(
            reranker_provider="unsupported",
            reranker_candidate_limit=2,
        ),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "node17",
            "mode": "keyword",
            "top_k": 1,
            "reranker_enabled": True,
        },
    )

    assert response.status_code == 200
    with sqlite_session_factory() as db:
        from app.models.retrieval import RetrievalLog

        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        assert log.retrieval_metadata["reranker_fallback"] is True
        assert log.retrieval_metadata["reranker_fallback_reason"] == "configuration_invalid"


def test_invalid_settings_limit_keeps_original_candidates_and_skips_provider(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    project_id = _seed_chunks(sqlite_session_factory, ["node17 evidence"])
    provider_calls = []

    class Provider:
        name = "multilingual_cross_encoder"

        def score(self, query, candidates):
            provider_calls.append(candidates)
            return [1.0 for _ in candidates]

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(
            reranker_provider="multilingual_cross_encoder",
            reranker_base_url="http://reranker.test",
            reranker_model="synthetic",
            reranker_candidate_limit=0,
        ),
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_reranker_provider_from_settings",
        lambda settings: Provider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "node17",
            "mode": "keyword",
            "top_k": 1,
            "reranker_enabled": True,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert provider_calls == []
    with sqlite_session_factory() as db:
        from app.models.retrieval import RetrievalLog

        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        assert log.retrieval_metadata["reranker_fallback"] is True
        assert log.retrieval_metadata["reranker_fallback_reason"] == "configuration_invalid"
