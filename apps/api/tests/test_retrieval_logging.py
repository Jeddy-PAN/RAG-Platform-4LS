import uuid

import numpy as np

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project
from app.models.retrieval import RetrievalLog, RetrievalLogChunk
from app.models.retrieval import RetrievalMode
from app.rag.retrieval.types import RetrievalCandidate
from app.services.retrieval_logs import create_retrieval_log


def test_retrieval_api_writes_logs(api_client, sqlite_session_factory) -> None:
    """Every retrieval API call should create log and result rows."""

    with sqlite_session_factory() as db:
        project = Project(name="Logging")
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
        chunk = Chunk(
            project_id=project.id,
            document_id=document.id,
            chunk_index=0,
            text="alpha logging policy",
            content_hash=str(uuid.uuid4()),
            embedding=[0.1] * 1024,
        )
        db.add(chunk)
        db.commit()
        project_id = project.id

    response = api_client.post(
        f"/api/projects/{project_id}/retrieval/query",
        json={"query": "alpha", "mode": "keyword", "top_k": 5},
    )

    assert response.status_code == 200
    with sqlite_session_factory() as db:
        logs = db.query(RetrievalLog).all()
        log_chunks = db.query(RetrievalLogChunk).all()

    assert len(logs) == 1
    assert logs[0].project_id == project_id
    assert logs[0].latency_ms is not None
    assert len(log_chunks) == 1
    assert log_chunks[0].project_id == project_id


def test_retrieval_log_accepts_numpy_scores(sqlite_session_factory) -> None:
    """Retrieval logging should persist pgvector-style numpy scalar metadata."""

    with sqlite_session_factory() as db:
        project = Project(name="Numpy Scores")
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
        chunk = Chunk(
            project_id=project.id,
            document_id=document.id,
            chunk_index=0,
            text="alpha logging policy",
            content_hash=str(uuid.uuid4()),
            embedding=[0.1] * 1024,
        )
        db.add(chunk)
        db.flush()

        create_retrieval_log(
            db=db,
            project_id=project.id,
            query="alpha",
            mode=RetrievalMode.hybrid,
            top_k=1,
            latency_ms=12,
            results=[
                RetrievalCandidate(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_name=document.filename,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    source_metadata={},
                    vector_score=np.float32(0.75),
                    fused_score=np.float32(0.75),
                    rank=1,
                    score_metadata={"normalized_vector_score": np.float32(1.0)},
                )
            ],
        )

    with sqlite_session_factory() as db:
        log_chunk = db.query(RetrievalLogChunk).one()

    assert log_chunk.vector_score == 0.75
    assert log_chunk.fused_score == 0.75
    assert log_chunk.score_metadata == {"normalized_vector_score": 1.0}


def test_retrieval_log_detail_api_returns_ranked_chunks(
    api_client,
    sqlite_session_factory,
) -> None:
    """Retrieval log detail should expose request settings and ranked chunk evidence."""

    with sqlite_session_factory() as db:
        project = Project(name="Log Detail")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="source.txt",
            storage_path="/tmp/source.txt",
            file_size_bytes=20,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        first = Chunk(
            project_id=project.id,
            document_id=document.id,
            chunk_index=0,
            text="first ranked chunk",
            content_hash=str(uuid.uuid4()),
            embedding=[0.1] * 1024,
        )
        second = Chunk(
            project_id=project.id,
            document_id=document.id,
            chunk_index=1,
            text="second ranked chunk",
            content_hash=str(uuid.uuid4()),
            embedding=[0.2] * 1024,
        )
        db.add_all([first, second])
        db.flush()
        lexical_metadata = {
            "keyword_exact_identifiers": 1,
            "keyword_exact_ascii_terms": 2,
            "keyword_exact_cjk_terms": 3,
            "keyword_contained_identifiers": 4,
            "keyword_ngram_matches": 5,
            "keyword_retrieval_mode": "keyword",
            "normalized_keyword_score": 1.0,
            "pre_rerank_rank": 2,
        }
        log = create_retrieval_log(
            db=db,
            project_id=project.id,
            query="ranked",
            mode=RetrievalMode.hybrid,
            top_k=2,
            latency_ms=15,
            metadata={"reranker_enabled": True},
            results=[
                RetrievalCandidate(
                    chunk_id=second.id,
                    document_id=document.id,
                    document_name=document.filename,
                    chunk_index=second.chunk_index,
                    text=second.text,
                    source_metadata={},
                    vector_score=0.5,
                    keyword_score=0.9,
                    fused_score=0.8,
                    rank=2,
                    score_metadata={"pre_rerank_rank": 1},
                ),
                RetrievalCandidate(
                    chunk_id=first.id,
                    document_id=document.id,
                    document_name=document.filename,
                    chunk_index=first.chunk_index,
                    text=first.text,
                    source_metadata={},
                    vector_score=0.7,
                    keyword_score=0.4,
                    fused_score=0.6,
                    rank=1,
                    score_metadata=lexical_metadata,
                ),
            ],
        )
        project_id = project.id
        log_id = log.id

    response = api_client.get(f"/api/projects/{project_id}/retrieval/logs/{log_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(log_id)
    assert body["query"] == "ranked"
    assert body["mode"] == "hybrid"
    assert body["top_k"] == 2
    assert body["retrieval_metadata"] == {"reranker_enabled": True}
    assert [chunk["rank"] for chunk in body["chunks"]] == [1, 2]
    assert body["chunks"][0]["text_preview"] == "first ranked chunk"
    assert body["chunks"][0]["document_name"] == "source.txt"
    assert body["chunks"][0]["score_metadata"] == lexical_metadata


def test_retrieval_log_detail_is_project_scoped(
    api_client,
    sqlite_session_factory,
) -> None:
    """Retrieval log detail should not cross project boundaries."""

    with sqlite_session_factory() as db:
        project = Project(name="Owner")
        other_project = Project(name="Other")
        db.add_all([project, other_project])
        db.flush()
        log = RetrievalLog(
            project_id=project.id,
            query="alpha",
            mode=RetrievalMode.keyword,
            top_k=1,
            retrieval_metadata={},
        )
        db.add(log)
        db.commit()
        other_project_id = other_project.id
        log_id = log.id

    response = api_client.get(f"/api/projects/{other_project_id}/retrieval/logs/{log_id}")

    assert response.status_code == 404


def test_evidence_plan_log_metadata_is_redacted_and_populated(
    sqlite_session_factory,
) -> None:
    """Generic evidence-facet logs carry redacted plan and coverage metadata."""

    import json

    from app.models.conversation import Message  # noqa: F401 (model import)
    from app.rag.retrieval.service import run_retrieval
    from app.rag.retrieval.evidence_types import EvidenceSelectionPlan

    with sqlite_session_factory() as db:
        project = Project(name=f"evidence-log-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document_ids: list[uuid.UUID] = []
        for filename, text in (
            ("logins.docx", "username node-17 alice"),
            ("passwords.docx", "password node-17 secret"),
        ):
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
                    text=text,
                    content_hash=str(uuid.uuid4()),
                )
            )
        db.commit()
        project_id = project.id

        result = run_retrieval(
            db,
            project_id=project_id,
            query="find the username and password for node-17",
            mode=RetrievalMode.keyword,
            top_k=8,
        )
        log = db.get(RetrievalLog, result.retrieval_log_id)

    metadata = log.retrieval_metadata
    plan = metadata["evidence_query_plan"]
    assert plan["facet_count"] == 2
    assert plan["facet_indexes"] == [0, 1]
    assert plan["route"] == "deterministic"

    selection = metadata["evidence_selection_plan"]
    assert len(selection["coverage"]) == 2
    assert all(item["status"] in ("covered", "unresolved", "conflicting") for item in selection["coverage"])
    selected_ids = {
        chunk_id
        for item in selection["coverage"]
        for chunk_id in item["selected_chunk_ids"]
    }
    assert selected_ids == {str(candidate.chunk_id) for candidate in result.results}

    serialized = json.dumps(metadata)
    assert "node-17" not in serialized
    assert "username" not in serialized
    assert "password" not in serialized
    assert "alice" not in serialized
    assert "secret" not in serialized
    assert "evidence_planner_latency_ms" in metadata
    assert metadata["evidence_planner_called"] is False
    assert metadata["evidence_assessor_called"] is False
    assert metadata["evidence_assessor_call_count"] == 0
    assert "evidence_selection_latency_ms" in metadata


def test_ordinary_single_fact_log_shape_is_backward_compatible(
    sqlite_session_factory,
) -> None:
    """Single-fact ordinary queries keep the existing log keys plus the plan."""

    from app.rag.retrieval.service import run_retrieval

    with sqlite_session_factory() as db:
        project = Project(name=f"single-log-{uuid.uuid4()}")
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
                text="escalation policy",
                content_hash=str(uuid.uuid4()),
            )
        )
        db.commit()
        project_id = project.id

        result = run_retrieval(
            db,
            project_id=project_id,
            query="what is escalation",
            mode=RetrievalMode.keyword,
            top_k=3,
        )
        log = db.get(RetrievalLog, result.retrieval_log_id)

    metadata = log.retrieval_metadata
    assert metadata["table_selection"] is None
    assert metadata["table_context"] is None
    assert metadata["evidence_selection"]["applied"] is True
    assert metadata["evidence_query_plan"]["facet_count"] == 1
    assert metadata["evidence_query_plan"]["facet_indexes"] == [0]
    assert "evidence_selection_plan" not in metadata


def test_table_compound_log_shape_is_backward_compatible(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Round 4A table logs remain unchanged and add no generic plan metadata."""

    import tests.test_retrieval_api as retrieval_api
    from app.rag.retrieval.service import run_retrieval

    project_id, first_id, second_id = retrieval_api.seed_two_named_tables(
        sqlite_session_factory
    )
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: retrieval_api.DeterministicEmbeddingProvider(),
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
        )
        log = db.get(RetrievalLog, result.retrieval_log_id)

    metadata = log.retrieval_metadata
    assert "table_query_plan" in metadata
    assert "evidence_query_plan" not in metadata
    assert metadata["table_query_plan"]["facet_count"] == 2
