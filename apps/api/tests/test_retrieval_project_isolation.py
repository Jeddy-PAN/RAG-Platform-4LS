import uuid

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project


def seed_project_chunk(db, name: str, text: str, embedding: list[float]) -> uuid.UUID:
    project = Project(name=name)
    db.add(project)
    db.flush()
    document = Document(
        project_id=project.id,
        filename=f"{name}.txt",
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
            text=text,
            content_hash=str(uuid.uuid4()),
            embedding=embedding,
        )
    )
    return project.id


def test_retrieval_never_crosses_project_boundaries(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Retrieval in one project must not return another project's chunks."""

    with sqlite_session_factory() as db:
        project_a = seed_project_chunk(
            db,
            "A",
            "alpha escalation policy",
            [0.1] * 1024,
        )
        project_b = seed_project_chunk(
            db,
            "B",
            "beta escalation policy",
            [0.9] * 1024,
        )
        db.commit()

    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider_from_settings",
        lambda: type("Provider", (), {"embed_texts": lambda self, texts: [[0.1] * 1024]})(),
    )

    for mode in ["vector", "keyword", "hybrid"]:
        response = api_client.post(
            f"/api/projects/{project_a}/retrieval/query",
            json={"query": "escalation", "mode": mode, "top_k": 5},
        )
        assert response.status_code == 200
        texts = [result["text_preview"] for result in response.json()["results"]]
        assert all("beta" not in text for text in texts)

        response_b = api_client.post(
            f"/api/projects/{project_b}/retrieval/query",
            json={"query": "escalation", "mode": mode, "top_k": 5},
        )
        assert response_b.status_code == 200
        texts_b = [result["text_preview"] for result in response_b.json()["results"]]
        assert all("alpha" not in text for text in texts_b)
