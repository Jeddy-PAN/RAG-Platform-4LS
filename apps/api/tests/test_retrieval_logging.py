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
                    score_metadata={"pre_rerank_rank": 2},
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
    assert body["chunks"][0]["score_metadata"] == {"pre_rerank_rank": 2}


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
