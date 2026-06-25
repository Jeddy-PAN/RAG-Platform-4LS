from pathlib import Path

from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest_document_job
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, IngestionJob, IngestionJobStatus
from app.models.project import Project


class FailingEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding unavailable")


class StaticEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


def test_ingestion_failure_marks_statuses(sqlite_session_factory, tmp_path: Path) -> None:
    """Failed first ingestion should mark job and document failed."""

    path = tmp_path / "source.txt"
    path.write_text("alpha beta", encoding="utf-8")

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name="Failure")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="source.txt",
            storage_path=str(path),
            file_size_bytes=path.stat().st_size,
            status=DocumentStatus.uploaded,
        )
        db.add(document)
        db.flush()
        job = IngestionJob(project_id=project.id, document_id=document.id)
        db.add(job)
        db.commit()

        ingest_document_job(
            db,
            job.id,
            project.id,
            document.id,
            embedding_provider=FailingEmbeddingProvider(),
        )

        db.refresh(document)
        db.refresh(job)

    assert job.status == IngestionJobStatus.failed
    assert document.status == DocumentStatus.failed
    assert "embedding unavailable" in (job.error_message or "")


def test_failed_reindex_preserves_existing_chunks(sqlite_session_factory, tmp_path: Path) -> None:
    """Failed reindex should not delete chunks from a previous good index."""

    path = tmp_path / "source.txt"
    path.write_text("alpha beta gamma", encoding="utf-8")

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name="Reindex")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="source.txt",
            storage_path=str(path),
            file_size_bytes=path.stat().st_size,
            status=DocumentStatus.uploaded,
        )
        db.add(document)
        db.flush()
        first_job = IngestionJob(project_id=project.id, document_id=document.id)
        db.add(first_job)
        db.commit()

        ingest_document_job(
            db,
            first_job.id,
            project.id,
            document.id,
            embedding_provider=StaticEmbeddingProvider(),
        )
        original_chunk_count = db.query(Chunk).count()

        second_job = IngestionJob(project_id=project.id, document_id=document.id)
        db.add(second_job)
        db.commit()
        ingest_document_job(
            db,
            second_job.id,
            project.id,
            document.id,
            embedding_provider=FailingEmbeddingProvider(),
        )

        db.refresh(document)
        db.refresh(second_job)
        final_chunk_count = db.query(Chunk).count()

    assert original_chunk_count > 0
    assert final_chunk_count == original_chunk_count
    assert second_job.status == IngestionJobStatus.failed
    assert document.status == DocumentStatus.indexed
