from pathlib import Path
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest_document_job
from app.ingestion.search_representation import CURRENT_SEARCH_REPRESENTATION_VERSION
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


class RecordingEmbeddingProvider:
    def __init__(self) -> None:
        self.inputs: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.inputs.append(list(texts))
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


def test_ingestion_embeds_search_text_and_stores_payload(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    """Provider inputs equal search_text while chunk.text stays the payload."""

    path = tmp_path / "source.txt"
    path.write_text("alpha beta gamma", encoding="utf-8")
    provider = RecordingEmbeddingProvider()

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name="Search Text")
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
            embedding_provider=provider,
        )
        db.refresh(document)
        chunks = db.query(Chunk).all()

    assert provider.inputs
    embedded = provider.inputs[0]
    assert len(embedded) == len(chunks)
    for chunk, search_text in zip(chunks, embedded, strict=True):
        assert chunk.search_text == search_text
        assert chunk.text == "alpha beta gamma"
        assert chunk.search_representation_version == CURRENT_SEARCH_REPRESENTATION_VERSION
        assert chunk.search_text.startswith("Document: source.txt")
        assert "alpha beta gamma" in chunk.search_text
    assert document.search_representation_version == CURRENT_SEARCH_REPRESENTATION_VERSION


def test_successful_reindex_leaves_one_active_current_generation(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    """A successful reindex keeps a single active generation at the current version."""

    path = tmp_path / "source.txt"
    path.write_text("alpha beta gamma delta", encoding="utf-8")

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name="Reindex Generations")
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
            embedding_provider=FakeEmbeddingProvider(),
        )
        second_job = IngestionJob(project_id=project.id, document_id=document.id)
        db.add(second_job)
        db.commit()
        ingest_document_job(
            db,
            second_job.id,
            project.id,
            document.id,
            embedding_provider=FakeEmbeddingProvider(),
        )

        db.refresh(document)
        active = db.query(Chunk).filter(Chunk.is_active.is_(True)).all()
        all_chunks = db.query(Chunk).all()

    assert len(active) == 1
    assert active[0].search_representation_version == CURRENT_SEARCH_REPRESENTATION_VERSION
    assert len(all_chunks) == 2
    assert {
        chunk.search_representation_version
        for chunk in all_chunks
        if chunk.is_active
    } == {CURRENT_SEARCH_REPRESENTATION_VERSION}
    assert document.search_representation_version == CURRENT_SEARCH_REPRESENTATION_VERSION


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
