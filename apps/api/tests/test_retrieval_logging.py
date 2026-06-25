import uuid

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project
from app.models.retrieval import RetrievalLog, RetrievalLogChunk


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
