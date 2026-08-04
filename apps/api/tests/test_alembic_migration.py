from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


API_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_database_url_engine(url: str):
    """Yield a committed connection to the isolated PostgreSQL database."""

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            yield connection
    finally:
        engine.dispose()


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


def test_search_representation_migration_contains_fields_and_trigger() -> None:
    """Round 2 migration should add search fields and a search_text trigger."""

    migration_file = API_ROOT / "alembic" / "versions" / "0004_add_search_representation.py"
    migration_text = migration_file.read_text()
    assert "search_text" in migration_text
    assert "search_representation_version" in migration_text
    assert "coalesce(NEW.search_text, NEW.text" in migration_text
    assert "UPDATE chunks SET search_text = text" in migration_text
    assert "legacy-v0" in migration_text


@pytest.mark.integration
def test_search_representation_fields_and_trigger(migrated_engine) -> None:
    """New fields exist and search_vector follows search_text with a text fallback."""

    with migrated_engine.begin() as connection:
        project_id = connection.execute(
            text("INSERT INTO projects (name) VALUES ('sr smoke') RETURNING id")
        ).scalar_one()
        document_id = connection.execute(
            text(
                """
                INSERT INTO documents (
                    project_id, filename, storage_path, file_size_bytes,
                    status, source_metadata
                )
                VALUES (:pid, 'sr.docx', '/tmp/sr.docx', 10, 'indexed', '{}'::jsonb)
                RETURNING id
                """
            ),
            {"pid": project_id},
        ).scalar_one()

        enriched_vector = connection.execute(
            text(
                """
                INSERT INTO chunks (
                    project_id, document_id, chunk_index, text, content_hash,
                    source_metadata, search_text
                )
                VALUES (
                    :pid, :did, 0, 'original payload', 'hash-a', '{}'::jsonb,
                    'enriched context'
                )
                RETURNING search_vector, search_representation_version
                """
            ),
            {"pid": project_id, "did": document_id},
        ).one()
        legacy_vector = connection.execute(
            text(
                """
                INSERT INTO chunks (
                    project_id, document_id, chunk_index, text, content_hash,
                    source_metadata
                )
                VALUES (
                    :pid, :did, 1, 'legacy fallback payload', 'hash-b', '{}'::jsonb
                )
                RETURNING search_vector, search_representation_version
                """
            ),
            {"pid": project_id, "did": document_id},
        ).one()

    assert "enriched" in enriched_vector[0]
    assert enriched_vector[1] == "legacy-v0"
    assert "legacy" in legacy_vector[0]
    assert legacy_vector[1] == "legacy-v0"


@pytest.mark.integration
def test_search_representation_migration_backfills_and_is_reversible(
    isolated_database_url,
) -> None:
    """0004 backfills legacy chunks and marks legacy documents reversibly.

    Uses a dedicated isolated database so the test is hermetic even though the
    session-scoped ``isolated_database_url`` fixture is shared across tests.
    """

    import uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import make_url

    source_url = make_url(isolated_database_url)
    base_name = source_url.database or "rag"
    database_name = f"{base_name}_test_{uuid.uuid4().hex[:12]}"
    maintenance_url = source_url.set(database="postgres")
    test_url = source_url.set(database=database_name).render_as_string(
        hide_password=False
    )

    admin = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin.dispose()

    try:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", test_url)

        command.upgrade(config, "0003_add_chunk_is_active")
        with isolated_database_url_engine(test_url) as connection:
            project_id = connection.execute(
                text("INSERT INTO projects (name) VALUES ('backfill project') RETURNING id")
            ).scalar_one()
            document_id = connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        project_id, filename, storage_path, file_size_bytes,
                        status, source_metadata
                    )
                    VALUES (:pid, 'legacy.txt', '/tmp/legacy.txt', 10, 'indexed', '{}'::jsonb)
                    RETURNING id
                    """
                ),
                {"pid": project_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO chunks (
                        project_id, document_id, chunk_index, text, content_hash,
                        source_metadata
                    )
                    VALUES (:pid, :did, 0, 'legacy body text', 'hash-legacy', '{}'::jsonb)
                    """
                ),
                {"pid": project_id, "did": document_id},
            )

        command.upgrade(config, "head")

        with isolated_database_url_engine(test_url) as connection:
            chunk = connection.execute(
                text(
                    """
                    SELECT search_text, search_representation_version
                    FROM chunks WHERE content_hash = 'hash-legacy'
                    """
                )
            ).one()
            document_version = connection.execute(
                text(
                    """
                    SELECT search_representation_version
                    FROM documents WHERE filename = 'legacy.txt'
                    """
                )
            ).scalar_one()
            assert chunk.search_text == "legacy body text"
            assert chunk.search_representation_version == "legacy-v0"
            assert document_version == "legacy-v0"

        command.downgrade(config, "0003_add_chunk_is_active")
        with isolated_database_url_engine(test_url) as connection:
            chunk_columns = connection.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'chunks' AND column_name = 'search_text'
                    """
                )
            ).scalar_one_or_none()
            assert chunk_columns is None

        command.upgrade(config, "head")
    finally:
        admin = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin.dispose()


@pytest.mark.integration
def test_search_representation_downgrade_recomputes_search_vector(
    isolated_database_url,
) -> None:
    """Downgrade recomputes search_vector from text, dropping enriched terms."""

    import uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import make_url

    source_url = make_url(isolated_database_url)
    base_name = source_url.database or "rag"
    database_name = f"{base_name}_test_{uuid.uuid4().hex[:12]}"
    maintenance_url = source_url.set(database="postgres")
    test_url = source_url.set(database=database_name).render_as_string(
        hide_password=False
    )

    admin = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin.dispose()

    try:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", test_url)
        command.upgrade(config, "head")
        with isolated_database_url_engine(test_url) as connection:
            project_id = connection.execute(
                text("INSERT INTO projects (name) VALUES ('sr') RETURNING id")
            ).scalar_one()
            document_id = connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        project_id, filename, storage_path, file_size_bytes,
                        status, source_metadata
                    )
                    VALUES (:p, 'f.txt', '/tmp/f.txt', 1, 'indexed', '{}'::jsonb)
                    RETURNING id
                    """
                ),
                {"p": project_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO chunks (
                        project_id, document_id, chunk_index, text, search_text,
                        content_hash, source_metadata
                    )
                    VALUES (:p, :d, 0, 'payload term only',
                            'enrichedonly payload term only', 'h', '{}'::jsonb)
                    """
                ),
                {"p": project_id, "d": document_id},
            )

        command.downgrade(config, "0003_add_chunk_is_active")

        with isolated_database_url_engine(test_url) as connection:
            search_vector = connection.execute(
                text(
                    "SELECT search_vector::text FROM chunks WHERE content_hash = 'h'"
                )
            ).scalar_one()
            assert "enrichedonly" not in search_vector
            assert "payload" in search_vector
    finally:
        admin = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin.dispose()
