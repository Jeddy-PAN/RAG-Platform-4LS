import pytest
from sqlalchemy.orm import Session

from app.rag.retrieval.vector import retrieve_vector
from tests.retrieval_test_helpers import seed_retrieval_chunk


def test_vector_retrieval_ranks_higher_similarity_first(sqlite_session_factory) -> None:
    """Vector retrieval should ignore missing embeddings and rank by similarity."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "close", "close", [1.0, 0.0])
        seed_retrieval_chunk(db, "far", "far", [0.0, 1.0])
        seed_retrieval_chunk(db, "missing", "missing", None)
        db.commit()

        results = retrieve_vector(db, project.id, [1.0, 0.0], top_k=5)

    assert [result.text for result in results] == ["close"]
    assert results[0].vector_score == pytest.approx(1.0)


def test_vector_retrieval_similarity_threshold_filters_results(sqlite_session_factory) -> None:
    """Weak vector matches should be removable through similarity_threshold."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "weak", "weak", [0.0, 1.0])
        db.commit()

        results = retrieve_vector(
            db,
            project.id,
            [1.0, 0.0],
            top_k=5,
            similarity_threshold=0.2,
        )

    assert results == []


@pytest.mark.integration
def test_vector_retrieval_works_against_postgresql(migrated_engine) -> None:
    """Vector retrieval should work against pgvector-backed rows."""

    with Session(migrated_engine) as db:
        project, _, _ = seed_retrieval_chunk(db, "pgvector", "postgres vector", [1.0] * 1024)
        db.commit()

        results = retrieve_vector(db, project.id, [1.0] * 1024, top_k=3)

    assert [result.text for result in results] == ["postgres vector"]
