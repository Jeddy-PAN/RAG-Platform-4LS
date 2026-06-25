import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project


@pytest.mark.integration
def test_chunk_queries_are_isolated_by_project_id(migrated_engine) -> None:
    """Project-scoped chunk queries should not mix knowledge bases."""

    with Session(migrated_engine) as session:
        project_a = Project(name="project a")
        project_b = Project(name="project b")
        session.add_all([project_a, project_b])
        session.flush()

        document_a = Document(
            project_id=project_a.id,
            filename="alpha.txt",
            storage_path="/tmp/alpha.txt",
            file_size_bytes=20,
            status=DocumentStatus.indexed,
        )
        document_b = Document(
            project_id=project_b.id,
            filename="beta.txt",
            storage_path="/tmp/beta.txt",
            file_size_bytes=20,
            status=DocumentStatus.indexed,
        )
        session.add_all([document_a, document_b])
        session.flush()

        session.add_all(
            [
                Chunk(
                    project_id=project_a.id,
                    document_id=document_a.id,
                    chunk_index=0,
                    text="alpha only knowledge",
                    content_hash="alpha-hash",
                ),
                Chunk(
                    project_id=project_b.id,
                    document_id=document_b.id,
                    chunk_index=0,
                    text="beta only knowledge",
                    content_hash="beta-hash",
                ),
            ]
        )
        session.commit()

        project_a_chunks = session.scalars(
            select(Chunk).where(Chunk.project_id == project_a.id)
        ).all()
        project_b_chunks = session.scalars(
            select(Chunk).where(Chunk.project_id == project_b.id)
        ).all()
        unscoped_chunks = session.scalars(
            select(Chunk).where(Chunk.document_id.in_([document_a.id, document_b.id]))
        ).all()

    assert [chunk.text for chunk in project_a_chunks] == ["alpha only knowledge"]
    assert [chunk.text for chunk in project_b_chunks] == ["beta only knowledge"]
    assert {chunk.text for chunk in unscoped_chunks} == {
        "alpha only knowledge",
        "beta only knowledge",
    }
