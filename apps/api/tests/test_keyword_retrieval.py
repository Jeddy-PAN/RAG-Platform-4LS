import pytest
from sqlalchemy.orm import Session

from app.rag.retrieval.keyword import retrieve_keyword
from tests.retrieval_test_helpers import seed_retrieval_chunk


def test_keyword_retrieval_ranks_matches_and_ignores_embedding(sqlite_session_factory) -> None:
    """Keyword retrieval should not require embedding provider access."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "keyword",
            "alpha alpha escalation",
            embedding=None,
        )
        seed_retrieval_chunk(db, "other", "unrelated policy", embedding=None)
        db.commit()

        results = retrieve_keyword(db, project.id, "alpha", top_k=5)

    assert [result.text for result in results] == ["alpha alpha escalation"]
    assert results[0].keyword_score == 2.0


def test_keyword_retrieval_rejects_empty_query_before_search(sqlite_session_factory) -> None:
    """Empty keyword queries should return no candidates."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "empty", "alpha", embedding=None)
        db.commit()

        results = retrieve_keyword(db, project.id, "   ", top_k=5)

    assert results == []


@pytest.mark.integration
def test_keyword_retrieval_works_against_postgresql_search_vector(migrated_engine) -> None:
    """Keyword retrieval should find PostgreSQL chunks scoped by project."""

    with Session(migrated_engine) as db:
        project, _, _ = seed_retrieval_chunk(
            db,
            "postgres-keyword",
            "postgres escalation policy",
            embedding=None,
        )
        db.commit()

        results = retrieve_keyword(db, project.id, "escalation", top_k=3)

    assert [result.text for result in results] == ["postgres escalation policy"]
