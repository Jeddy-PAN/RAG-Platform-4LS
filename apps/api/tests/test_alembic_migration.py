from pathlib import Path

import pytest
from sqlalchemy import text


API_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_configuration_files_exist() -> None:
    """Alembic should have the files needed to run migrations locally."""

    assert (API_ROOT / "alembic.ini").is_file()
    assert (API_ROOT / "alembic" / "env.py").is_file()
    assert (API_ROOT / "alembic" / "script.py.mako").is_file()


def test_initial_migration_contains_search_vector_trigger() -> None:
    """Initial migration should define pgvector and chunk keyword search."""

    migration_file = API_ROOT / "alembic" / "versions" / "0001_initial_schema.py"

    migration_text = migration_file.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration_text
    assert "chunks_search_vector_update" in migration_text
    assert "to_tsvector('simple'" in migration_text


def test_chat_metrics_migration_contains_request_observability_table() -> None:
    """Chat metrics migration should add request-level observability storage."""

    migration_file = API_ROOT / "alembic" / "versions" / "0002_chat_request_metrics.py"

    migration_text = migration_file.read_text()
    assert "chat_request_metrics" in migration_text
    assert "latency_ms" in migration_text
    assert "retrieval_latency_ms" in migration_text
    assert "generation_latency_ms" in migration_text
    assert "ix_chat_request_metrics_project_created" in migration_text


@pytest.mark.integration
def test_initial_migration_applies_pgvector_and_search_trigger(migrated_engine) -> None:
    """Applied schema should enable pgvector and populate chunk search vectors."""

    with migrated_engine.begin() as connection:
        vector_installed = connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()

        connection.execute(
            text(
                """
                INSERT INTO projects (name)
                VALUES ('migration smoke project')
                RETURNING id
                """
            )
        ).scalar_one()

        project_id = connection.execute(
            text("SELECT id FROM projects WHERE name = 'migration smoke project'")
        ).scalar_one()

        document_id = connection.execute(
            text(
                """
                INSERT INTO documents (
                    project_id,
                    filename,
                    storage_path,
                    file_size_bytes,
                    status,
                    source_metadata
                )
                VALUES (
                    :project_id,
                    'source.txt',
                    '/tmp/source.txt',
                    12,
                    'uploaded',
                    '{}'::jsonb
                )
                RETURNING id
                """
            ),
            {"project_id": project_id},
        ).scalar_one()

        search_vector = connection.execute(
            text(
                """
                INSERT INTO chunks (
                    project_id,
                    document_id,
                    chunk_index,
                    text,
                    content_hash,
                    source_metadata
                )
                VALUES (
                    :project_id,
                    :document_id,
                    0,
                    'alpha project knowledge',
                    'hash-alpha',
                    '{}'::jsonb
                )
                RETURNING search_vector
                """
            ),
            {"project_id": project_id, "document_id": document_id},
        ).scalar_one()

    assert vector_installed
    assert search_vector is not None


@pytest.mark.integration
def test_initial_migration_can_downgrade_and_upgrade(isolated_database_url) -> None:
    """Initial migration should be reversible for local development rebuilds."""

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
