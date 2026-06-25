from pathlib import Path
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingestion.chunker import ChunkCandidate, chunk_sections
from app.ingestion.parsers import get_parser_for_path
from app.ingestion.status import mark_completed, mark_failed, mark_running
from app.models.chunk import Chunk
from app.models.document import (
    Document,
    DocumentSection,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)
from app.rag.providers.embeddings import OpenAIEmbeddingProvider
from app.rag.providers.types import EmbeddingProvider


def ingest_document_job(
    db: Session,
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    embedding_provider: EmbeddingProvider | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> None:
    """Run the project-scoped ingestion pipeline for one queued job."""

    job = db.get(IngestionJob, job_id)
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.project_id == project_id,
        )
    )
    if job is None:
        return
    if document is None or job.project_id != project_id or job.document_id != document_id:
        mark_failed(db, job, None, "Document not found for project")
        return

    was_indexed = document.status == DocumentStatus.indexed
    try:
        mark_running(db, job, document)
        path = Path(document.storage_path)
        if not path.exists():
            raise FileNotFoundError(f"Stored file not found: {path}")

        parser = get_parser_for_path(path)
        parsed_sections = parser.parse(path)
        chunk_candidates = chunk_sections(
            project_id,
            document_id,
            parsed_sections,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunk_candidates:
            raise ValueError("Document contains no usable text chunks")

        provider = embedding_provider or OpenAIEmbeddingProvider.from_settings()
        vectors = provider.embed_texts([candidate.text for candidate in chunk_candidates])

        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.execute(delete(DocumentSection).where(DocumentSection.document_id == document_id))
        db.flush()

        section_rows = [
            DocumentSection(
                project_id=project_id,
                document_id=document_id,
                section_index=section.section_index,
                text=section.text,
                source_metadata=section.source_metadata,
            )
            for section in parsed_sections
        ]
        db.add_all(section_rows)
        db.flush()
        sections_by_index = {section.section_index: section for section in section_rows}

        db.add_all(
            _build_chunk_rows(project_id, document_id, chunk_candidates, vectors, sections_by_index)
        )
        mark_completed(db, job, document)
    except Exception as exc:
        db.rollback()
        mark_failed(
            db,
            job,
            document,
            str(exc),
            preserve_indexed_document=was_indexed,
        )


def _build_chunk_rows(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    candidates: list[ChunkCandidate],
    vectors: list[list[float]],
    sections_by_index: dict[int, DocumentSection],
) -> list[Chunk]:
    """Convert chunk candidates and embeddings into ORM rows."""

    return [
        Chunk(
            project_id=project_id,
            document_id=document_id,
            section_id=sections_by_index[candidate.section_index].id,
            chunk_index=candidate.chunk_index,
            text=candidate.text,
            token_count=candidate.token_count,
            content_hash=candidate.content_hash,
            source_metadata=candidate.source_metadata,
            embedding=vector,
        )
        for candidate, vector in zip(candidates, vectors, strict=True)
    ]
