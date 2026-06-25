from pathlib import Path
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest_document_job
from app.models.chunk import Chunk
from app.models.document import (
    Document,
    DocumentSection,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)
from app.models.project import Project


class FakeEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


def test_ingestion_pipeline_creates_sections_and_chunks(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    """Successful ingestion should index sections and embedded chunks."""

    path = tmp_path / "source.txt"
    path.write_text("alpha beta gamma delta", encoding="utf-8")

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name="Ingestion")
        db.add(project)
        db.flush()
        project_id = project.id
        document = Document(
            project_id=project_id,
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
            embedding_provider=FakeEmbeddingProvider(),
            chunk_size=3,
            chunk_overlap=1,
        )

        db.refresh(document)
        db.refresh(job)
        sections = db.query(DocumentSection).all()
        chunks = db.query(Chunk).all()

    assert job.status == IngestionJobStatus.completed
    assert document.status == DocumentStatus.indexed
    assert [section.text for section in sections] == ["alpha beta gamma delta"]
    assert [chunk.project_id for chunk in chunks] == [project_id, project_id]
    assert all(chunk.embedding for chunk in chunks)


def test_ingestion_pipeline_requires_project_scoped_document(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    """Pipeline must not load documents by document_id alone."""

    path = tmp_path / "source.txt"
    path.write_text("alpha", encoding="utf-8")

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name="Correct")
        other_project_id = uuid.uuid4()
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
            other_project_id,
            document.id,
            embedding_provider=FakeEmbeddingProvider(),
        )

        db.refresh(document)
        db.refresh(job)

    assert job.status == IngestionJobStatus.failed
    assert document.status == DocumentStatus.uploaded
    assert "not found" in (job.error_message or "")


@pytest.mark.integration
def test_ingestion_pipeline_writes_chunks_to_postgresql(
    migrated_engine,
    tmp_path: Path,
) -> None:
    """Successful ingestion should insert vector chunks in PostgreSQL."""

    path = tmp_path / "postgres-source.txt"
    path.write_text("postgres alpha beta gamma", encoding="utf-8")

    with Session(migrated_engine) as db:
        project = Project(name="Postgres Ingestion")
        db.add(project)
        db.flush()
        project_id = project.id
        document = Document(
            project_id=project_id,
            filename="postgres-source.txt",
            storage_path=str(path),
            file_size_bytes=path.stat().st_size,
            status=DocumentStatus.uploaded,
        )
        db.add(document)
        db.flush()
        job = IngestionJob(project_id=project_id, document_id=document.id)
        db.add(job)
        db.commit()

        ingest_document_job(
            db,
            job.id,
            project_id,
            document.id,
            embedding_provider=FakeEmbeddingProvider(),
        )

        chunk_count = db.query(Chunk).filter(Chunk.project_id == project_id).count()
        search_vector = db.execute(text("SELECT search_vector FROM chunks LIMIT 1")).scalar_one()

    assert chunk_count == 1
    assert search_vector is not None
