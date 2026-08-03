import math
import uuid

import numpy as np

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project
from app.models.retrieval import RetrievalLog
from app.rag.retrieval.types import RetrievalCandidate, RetrievalResult


class DeterministicEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


def seed_two_named_tables(
    sqlite_session_factory,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create two indexed DOCX-like tables with only synthetic values."""

    with sqlite_session_factory() as db:
        project = Project(name=f"compound-tables-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document_ids: list[uuid.UUID] = []
        definitions = (
            ("alpha-inventory.docx", ["ServerName"], ["alpha-01", "alpha-02"]),
            ("beta-access.docx", ["Label", "State"], ["beta-01", "beta-02"]),
        )
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
        return project.id, document_ids[0], document_ids[1]


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


def seed_chunks(sqlite_session_factory, texts: list[str]) -> uuid.UUID:
    """Insert multiple chunks in one project for ranking tests."""

    with sqlite_session_factory() as db:
        project = Project(name=f"Project {uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="source.txt",
            storage_path="/tmp/source.txt",
            file_size_bytes=sum(len(text) for text in texts),
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
                    embedding=[0.1] * 1024,
                )
            )
        db.commit()
        return project.id


def seed_low_relevance_table(sqlite_session_factory) -> uuid.UUID:
    """Insert a strong paragraph and a weak table candidate in one project."""

    with sqlite_session_factory() as db:
        project = Project(name=f"Fallback {uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="handbook.docx",
            storage_path="/tmp/handbook.docx",
            file_size_bytes=100,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        db.add_all(
            [
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=0,
                    text="Relevant ordinary paragraph",
                    content_hash=str(uuid.uuid4()),
                    embedding=[1.0] + [0.0] * 1023,
                    source_metadata={"type": "paragraph"},
                ),
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=1,
                    text="Unrelated inventory table",
                    content_hash=str(uuid.uuid4()),
                    embedding=[0.1, math.sqrt(0.99)] + [0.0] * 1022,
                    source_metadata={
                        "type": "table",
                        "table_index": 0,
                        "table_chunk_type": "table",
                        "headers": ["InventoryCode"],
                        "data_row_start": 1,
                        "data_row_end": 1,
                        "total_rows": 1,
                    },
                ),
            ]
        )
        db.commit()
        return project.id


def test_retrieval_api_returns_debug_fields(api_client, sqlite_session_factory, monkeypatch):
    """Retrieval API should return scored results and a log id."""

    project_id = seed_chunk(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
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
    score_metadata = body["results"][0]["score_metadata"]
    assert score_metadata["fusion_method"] == "weighted_rrf"
    assert score_metadata["vector_rank"] == 1
    assert score_metadata["keyword_rank"] == 1
    assert score_metadata["vector_rrf_score"] > 0
    assert score_metadata["keyword_rrf_score"] > 0
    assert score_metadata["evidence_selection_reason"] == "ranked_fill"

    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(body["retrieval_log_id"]))
        logged_chunk = log.chunks[0]

    assert log.retrieval_metadata["evidence_selection"] == {
        "applied": True,
        "policy": "strong_lexical_then_ranked_fill",
    }
    assert logged_chunk.score_metadata["fusion_method"] == "weighted_rrf"
    assert logged_chunk.score_metadata["vector_rank"] == 1
    assert logged_chunk.score_metadata["keyword_rank"] == 1


def test_full_table_query_without_table_candidates_falls_back_to_normal_top_k(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """A table-shaped query must preserve normal retrieval when no table exists."""

    project_id = seed_chunks(
        sqlite_session_factory,
        ["first ordinary paragraph", "second ordinary paragraph"],
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "list all rows", "mode": "vector", "top_k": 1},
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        assert log.retrieval_metadata["table_selection"]["status"] == "none"
        assert log.retrieval_metadata["expansion_applied"] is False


def test_keyword_mode_selects_containment_from_beyond_initial_top_k(
    api_client,
    sqlite_session_factory,
) -> None:
    """Final selection must see strong lexical evidence below general-term hits."""

    with sqlite_session_factory() as db:
        project = Project(name=f"Keyword pool {uuid.uuid4()}")
        db.add(project)
        db.flush()
        rows = [
            (f"general-{index}.txt", "alpha beta gamma delta")
            for index in range(4)
        ] + [("containment.txt", "node01 standby")]
        containment_document_id = None
        for index, (filename, text) in enumerate(rows):
            document = Document(
                project_id=project.id,
                filename=filename,
                storage_path=f"/tmp/{filename}",
                file_size_bytes=len(text),
                status=DocumentStatus.indexed,
            )
            db.add(document)
            db.flush()
            if filename == "containment.txt":
                containment_document_id = document.id
            db.add(
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=0,
                    text=text,
                    content_hash=f"keyword-pool-{index}",
                )
            )
        db.commit()
        project_id = project.id

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "node01-east alpha beta gamma delta",
            "mode": "keyword",
            "top_k": 2,
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    containment = next(
        result for result in results
        if result["document_id"] == str(containment_document_id)
    )
    assert containment["keyword_score"] == 3.0
    assert containment["score_metadata"]["contained_identifiers"] == 1
    assert containment["score_metadata"]["evidence_selection_reason"] == (
        "protected_contained_identifier"
    )


def test_low_scoring_table_falls_back_to_stronger_normal_result(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """An insufficient table score must not replace the ordinary top result."""

    project_id = seed_low_relevance_table(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type(
            "Provider",
            (),
            {"embed_texts": lambda self, texts: [[1.0] + [0.0] * 1023]},
        )(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "list all rows", "mode": "vector", "top_k": 1},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["text_preview"] == "Relevant ordinary paragraph"
    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        assert log.retrieval_metadata["table_selection"]["status"] == "insufficient_score"
        assert log.retrieval_metadata["expansion_applied"] is False


def test_retrieval_api_can_rerank_wider_candidate_set(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Reranker should reorder initial retrieval candidates before final top_k."""

    project_id = seed_chunks(
        sqlite_session_factory,
        [
            "alpha alpha filler",
            "alpha filler",
            "google sycamore quantum supremacy",
        ],
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "google sycamore quantum supremacy",
            "mode": "vector",
            "top_k": 1,
            "reranker_enabled": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["text_preview"] == "google sycamore quantum supremacy"
    assert body["results"][0]["score_metadata"]["reranker"] == "keyword_overlap"
    assert body["results"][0]["score_metadata"]["pre_rerank_rank"] > 1
    assert body["results"][0]["score_metadata"]["evidence_selection_reason"] == "ranked_fill"


def test_retrieval_api_serializes_numpy_scores(
    api_client,
    monkeypatch,
) -> None:
    """Retrieval responses should normalize numpy scalar scores to JSON floats."""

    monkeypatch.setattr(
        "app.api.retrieval.run_retrieval",
        lambda *args, **kwargs: RetrievalResult(
            query="alpha",
            mode="hybrid",
            top_k=1,
            latency_ms=1,
            retrieval_log_id=uuid.uuid4(),
            results=[
                RetrievalCandidate(
                    chunk_id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    document_name="source.txt",
                    chunk_index=0,
                    text="alpha",
                    source_metadata={"page": np.int64(1)},
                    vector_score=np.float32(0.75),
                    fused_score=np.float32(0.75),
                    score_metadata={"normalized_vector_score": np.float32(1.0)},
                    rank=1,
                )
            ],
        ),
    )

    response = api_client.post(
        f"/api/projects/{uuid.uuid4()}/retrieval/query",
        json={"query": "alpha", "mode": "hybrid", "top_k": 3},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert isinstance(result["vector_score"], float)
    assert isinstance(result["fused_score"], float)
    assert isinstance(result["source_metadata"]["page"], int)
    assert isinstance(result["score_metadata"]["normalized_vector_score"], float)


def test_vector_retrieval_embeds_query_once(api_client, sqlite_session_factory, monkeypatch):
    """Vector retrieval should embed the query exactly once."""

    project_id = seed_chunk(sqlite_session_factory)
    calls = []

    class Provider:
        def embed_texts(self, texts):
            calls.append(texts)
            return [[0.1] * 1024]

    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
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
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
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
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
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


def test_compound_full_table_query_expands_both_tables(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """A compound full-table query must retrieve and expand every resolved table."""

    project_id, first_id, second_id = seed_two_named_tables(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: DeterministicEmbeddingProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": (
                "列出 Alpha Inventory 表格中的所有 server"
                "和列出 Beta Access table 的所有行"
            ),
            "mode": "hybrid",
            "top_k": 8,
        },
    )

    assert response.status_code == 200
    assert {item["document_id"] for item in response.json()["results"]} == {
        str(first_id),
        str(second_id),
    }

    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        metadata = log.retrieval_metadata
        plan_metadata = metadata["table_query_plan"]
        assert [facet["status"] for facet in plan_metadata["facets"]] == [
            "selected",
            "selected",
        ]
        assert plan_metadata["distinct_selected_table_count"] == 2
        assert len(plan_metadata["table_contexts"]) == 2
        assert all(not context["is_partial"] for context in plan_metadata["table_contexts"])
        assert metadata["evidence_selection"]["applied"] is False


def test_ordinary_username_password_query_stays_single_facet(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Ordinary attribute queries must never enter compound table expansion."""

    project_id = seed_chunk(
        sqlite_session_factory,
        text="username alice password secret",
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: DeterministicEmbeddingProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "find the username and password for node77-east",
            "mode": "hybrid",
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"]
    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        assert "table_query_plan" not in log.retrieval_metadata


def test_route_helper_preserves_candidate_limits(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Extracted route helper must keep each mode's exact candidate pool width."""

    project_id = seed_chunk(sqlite_session_factory)
    captured: dict[str, int] = {}

    def fake_keyword(db, project_id, query, candidate_limit, document_id=None):
        captured["keyword"] = candidate_limit
        return []

    def fake_vector(
        db,
        project_id,
        embedding,
        candidate_limit,
        similarity_threshold=0.0,
        document_id=None,
    ):
        captured["vector"] = candidate_limit
        return []

    def fake_fuse(vector_candidates, keyword_candidates, top_k, vector_weight, keyword_weight):
        captured["hybrid"] = top_k
        return []

    monkeypatch.setattr("app.rag.retrieval.service.retrieve_keyword", fake_keyword)
    monkeypatch.setattr("app.rag.retrieval.service.retrieve_vector", fake_vector)
    monkeypatch.setattr("app.rag.retrieval.service.fuse_retrieval_results", fake_fuse)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: DeterministicEmbeddingProvider(),
    )

    api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "keyword", "top_k": 2},
    )
    assert captured["keyword"] == max(2, 2 * 3, 20)

    api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "vector", "top_k": 2},
    )
    assert captured["vector"] == 2

    api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "hybrid", "top_k": 2},
    )
    assert captured["hybrid"] == max(2 * 3, 20, 2)

    api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "list all rows", "mode": "hybrid", "top_k": 2},
    )
    assert captured["hybrid"] == max(2 * 5 * 3, 40 * 3, 60)


def test_compound_plan_with_ambiguous_facet_returns_no_results(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """An ambiguous compound facet must gate generation with empty results."""

    project_id, first_id, second_id = seed_two_named_tables(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: DeterministicEmbeddingProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "列出 Alpha Inventory 表格中的所有 server和列出所有行",
            "mode": "hybrid",
            "top_k": 8,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        plan_metadata = log.retrieval_metadata["table_query_plan"]
        assert plan_metadata["can_generate"] is False
        assert plan_metadata["requires_clarification"] is True
        assert plan_metadata["pending_clarification_index"] == 1
        assert [facet["status"] for facet in plan_metadata["facets"]] == [
            "selected",
            "ambiguous",
        ]


def test_compound_plan_with_missing_facet_returns_no_results(
    api_client,
    sqlite_session_factory,
) -> None:
    """A facet with no candidates must not claim complete expansion."""

    project_id, first_id, second_id = seed_two_named_tables(sqlite_session_factory)

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={
            "query": "列出 Alpha Inventory 表格中的所有 server和列出 zzzz 的所有行",
            "mode": "keyword",
            "top_k": 8,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    with sqlite_session_factory() as db:
        log = db.get(RetrievalLog, uuid.UUID(response.json()["retrieval_log_id"]))
        plan_metadata = log.retrieval_metadata["table_query_plan"]
        assert plan_metadata["can_generate"] is False
        assert plan_metadata["requires_clarification"] is False
        assert [facet["status"] for facet in plan_metadata["facets"]] == [
            "selected",
            "none",
        ]


def test_compound_document_scope_applies_per_facet(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Document restriction must constrain every compound facet independently."""

    from app.models.retrieval import RetrievalMode
    from app.rag.retrieval.service import run_retrieval

    project_id, first_id, second_id = seed_two_named_tables(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: DeterministicEmbeddingProvider(),
    )

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query=(
                "列出 Alpha Inventory 表格中的所有 server"
                "和列出 Beta Access table 的所有行"
            ),
            mode=RetrievalMode.hybrid,
            top_k=8,
            document_id=first_id,
        )

    assert result.results
    assert {candidate.document_id for candidate in result.results} == {first_id}
    assert result.table_selection_plan is not None
    assert all(
        outcome.selected is None or outcome.selected.document_id == first_id
        for outcome in result.table_selection_plan.outcomes
    )


def test_compound_stale_preferred_facet_index_is_ignored(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """A stale preferred facet index must not raise a server error."""

    from app.models.retrieval import RetrievalMode
    from app.rag.retrieval.service import run_retrieval

    project_id, first_id, second_id = seed_two_named_tables(sqlite_session_factory)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: DeterministicEmbeddingProvider(),
    )

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query=(
                "列出 Alpha Inventory 表格中的所有 server"
                "和列出 Beta Access table 的所有行"
            ),
            mode=RetrievalMode.hybrid,
            top_k=8,
            preferred_tables_by_facet={3: (first_id, 0)},
        )

    assert result.table_selection_plan is not None
    assert result.results
    assert [facet["status"] for facet in result.table_selection_plan.to_metadata()["facets"]] == [
        "selected",
        "selected",
    ]
