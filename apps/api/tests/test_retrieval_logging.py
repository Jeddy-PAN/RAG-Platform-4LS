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
