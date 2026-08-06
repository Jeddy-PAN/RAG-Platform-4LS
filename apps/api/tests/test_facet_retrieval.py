"""Tests for Round 4B bounded per-facet ordinary recall."""

import uuid

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project
from app.models.retrieval import RetrievalMode
from app.rag.retrieval.service import run_retrieval


class RecordingEmbeddingProvider:
    def __init__(self) -> None:
        self.inputs: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.inputs.append(list(texts))
        return [[0.1] * 1024 for _ in texts]


def _seed_facet_documents(sqlite_session_factory):
    """Seed one project with a username document and a password document."""

    with sqlite_session_factory() as db:
        project = Project(name=f"facet-retrieval-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document_ids: dict[str, uuid.UUID] = {}
        for label, filename in (
            ("login", "logins.docx"),
            ("password", "passwords.docx"),
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
            document_ids[label] = document.id
        db.add(
            Chunk(
                project_id=project.id,
                document_id=document_ids["login"],
                chunk_index=0,
                text="username node-17 alice",
                content_hash=str(uuid.uuid4()),
                embedding=[0.1] * 1024,
            )
        )
        db.add(
            Chunk(
                project_id=project.id,
                document_id=document_ids["password"],
                chunk_index=0,
                text="password node-17 secret",
                content_hash=str(uuid.uuid4()),
                embedding=[0.1] * 1024,
            )
        )
        db.commit()
        return project.id, document_ids


def test_one_entity_two_attributes_retrieves_support_from_two_documents(
    sqlite_session_factory,
) -> None:
    project_id, document_ids = _seed_facet_documents(sqlite_session_factory)

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query="find the username and password for node-17",
            mode=RetrievalMode.keyword,
            top_k=8,
        )

    assert result.evidence_query_plan is not None
    assert len(result.evidence_query_plan.facets) == 2
    assert {candidate.document_id for candidate in result.results} == set(
        document_ids.values()
    )


def test_same_chunk_supports_two_facets_is_deduplicated(
    sqlite_session_factory,
) -> None:
    with sqlite_session_factory() as db:
        project = Project(name=f"shared-facet-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="combined.docx",
            storage_path="/tmp/combined.docx",
            file_size_bytes=100,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        chunk = Chunk(
            project_id=project.id,
            document_id=document.id,
            chunk_index=0,
            text="node-17 username node-17 password node-17",
            content_hash=str(uuid.uuid4()),
        )
        db.add(chunk)
        db.commit()
        project_id = project.id
        chunk_id = chunk.id

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query="find the username and password for node-17",
            mode=RetrievalMode.keyword,
            top_k=8,
        )

    matching = [candidate for candidate in result.results if candidate.chunk_id == chunk_id]
    assert len(matching) == 1
    assert matching[0].score_metadata["evidence_facet_indexes"] == [0, 1]


def test_vector_hybrid_batches_facet_embeddings_once(
    sqlite_session_factory,
) -> None:
    project_id, _ = _seed_facet_documents(sqlite_session_factory)
    provider = RecordingEmbeddingProvider()

    with sqlite_session_factory() as db:
        run_retrieval(
            db,
            project_id=project_id,
            query="find the username and password for node-17",
            mode=RetrievalMode.hybrid,
            top_k=8,
            embedding_provider=provider,
        )

    assert len(provider.inputs) == 1
    assert provider.inputs[0] == ["username node-17", "password node-17"]


def test_keyword_mode_never_requests_embeddings(
    sqlite_session_factory,
) -> None:
    project_id, _ = _seed_facet_documents(sqlite_session_factory)

    def fail_if_called():
        raise AssertionError("embedding provider should not be used")

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query="find the username and password for node-17",
            mode=RetrievalMode.keyword,
            top_k=8,
            embedding_provider=fail_if_called,  # type: ignore[arg-type]
        )

    assert result.results


def test_document_isolation_applies_to_every_facet(
    sqlite_session_factory,
) -> None:
    project_id, document_ids = _seed_facet_documents(sqlite_session_factory)

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query="find the username and password for node-17",
            mode=RetrievalMode.keyword,
            top_k=8,
            document_id=document_ids["login"],
        )

    assert {candidate.document_id for candidate in result.results} == {
        document_ids["login"]
    }
    assert document_ids["password"] not in {
        candidate.document_id for candidate in result.results
    }


def test_single_fact_question_keeps_single_facet_plan(
    sqlite_session_factory,
) -> None:
    with sqlite_session_factory() as db:
        project = Project(name=f"single-fact-{uuid.uuid4()}")
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

    with sqlite_session_factory() as db:
        result = run_retrieval(
            db,
            project_id=project_id,
            query="what is escalation",
            mode=RetrievalMode.keyword,
            top_k=3,
        )

    assert result.evidence_query_plan is not None
    assert len(result.evidence_query_plan.facets) == 1
    assert result.results
