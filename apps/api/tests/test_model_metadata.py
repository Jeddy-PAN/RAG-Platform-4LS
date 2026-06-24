from app.db.base import Base
import app.models  # noqa: F401


PROJECT_SCOPED_TABLES = {
    "documents",
    "document_sections",
    "ingestion_jobs",
    "chunks",
    "conversations",
    "messages",
    "message_citations",
    "retrieval_logs",
    "retrieval_log_chunks",
    "feedback",
    "eval_datasets",
    "eval_questions",
    "eval_runs",
    "eval_results",
}


def test_expected_tables_are_registered() -> None:
    """All v1 tables should be visible through SQLAlchemy metadata."""

    assert {
        "app_settings",
        "projects",
        *PROJECT_SCOPED_TABLES,
    }.issubset(Base.metadata.tables.keys())


def test_project_scoped_tables_have_project_id() -> None:
    """Every project-owned table must carry a non-null project_id."""

    for table_name in PROJECT_SCOPED_TABLES:
        table = Base.metadata.tables[table_name]
        assert "project_id" in table.columns, f"{table_name} must include project_id"
        assert not table.columns["project_id"].nullable


def test_chunks_have_vector_and_search_columns() -> None:
    """Chunks must support both vector retrieval and keyword retrieval."""

    chunks = Base.metadata.tables["chunks"]

    assert "embedding" in chunks.columns
    assert "search_vector" in chunks.columns
