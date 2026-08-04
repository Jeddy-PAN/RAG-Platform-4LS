import pytest

from app.ingestion.search_representation import CURRENT_SEARCH_REPRESENTATION_VERSION
from app.models.document import Document, DocumentStatus, IngestionJob
from app.models.project import Project


def create_project(api_client, name: str = "Docs") -> str:
    response = api_client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("source.pdf", "application/pdf"),
        ("source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("source.md", "text/markdown"),
        ("source.txt", "text/plain"),
        ("source.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ],
)
def test_upload_supported_document_creates_document_and_job(
    api_client, monkeypatch, tmp_path, filename: str, content_type: str
) -> None:
    """Uploading a supported file should create document and ingestion job rows."""

    calls = []
    monkeypatch.setattr("app.services.storage.get_upload_root", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.documents.enqueue_ingestion_job",
        lambda **payload: calls.append(payload),
    )
    project_id = create_project(api_client)

    response = api_client.post(
        f"/api/projects/{project_id}/documents",
        files={"file": (filename, b"document bytes", content_type)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["filename"] == filename
    assert body["document"]["project_id"] == project_id
    assert body["document"]["status"] == "uploaded"
    assert body["ingestion_job"]["status"] == "queued"
    assert calls[0]["project_id"] == project_id
    assert calls[0]["document_id"] == body["document"]["id"]


def test_upload_rejects_unsupported_and_empty_files(api_client, monkeypatch, tmp_path) -> None:
    """Document upload should reject files that cannot enter ingestion."""

    monkeypatch.setattr("app.services.storage.get_upload_root", lambda: tmp_path)
    project_id = create_project(api_client)

    unsupported = api_client.post(
        f"/api/projects/{project_id}/documents",
        files={"file": ("malware.exe", b"content", "application/octet-stream")},
    )
    empty = api_client.post(
        f"/api/projects/{project_id}/documents",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert unsupported.status_code == 400
    assert empty.status_code == 400


def test_upload_queue_failure_marks_job_failed(api_client, monkeypatch, tmp_path) -> None:
    """Queue failures should not be reported as successful uploads."""

    def fail_enqueue(**payload) -> None:
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.services.storage.get_upload_root", lambda: tmp_path)
    monkeypatch.setattr("app.services.documents.enqueue_ingestion_job", fail_enqueue)
    project_id = create_project(api_client)

    response = api_client.post(
        f"/api/projects/{project_id}/documents",
        files={"file": ("source.txt", b"content", "text/plain")},
    )

    assert response.status_code == 503


def test_list_get_delete_and_reindex_documents(api_client, monkeypatch, tmp_path) -> None:
    """Document endpoints should operate inside the selected project."""

    calls = []
    monkeypatch.setattr("app.services.storage.get_upload_root", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.documents.enqueue_ingestion_job",
        lambda **payload: calls.append(payload),
    )
    project_id = create_project(api_client)
    upload = api_client.post(
        f"/api/projects/{project_id}/documents",
        files={"file": ("source.txt", b"content", "text/plain")},
    ).json()
    document_id = upload["document"]["id"]

    list_response = api_client.get(f"/api/projects/{project_id}/documents")
    get_response = api_client.get(f"/api/projects/{project_id}/documents/{document_id}")
    reindex_response = api_client.post(
        f"/api/projects/{project_id}/documents/{document_id}/reindex"
    )
    delete_response = api_client.delete(
        f"/api/projects/{project_id}/documents/{document_id}"
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [document_id]
    assert get_response.status_code == 200
    assert reindex_response.status_code == 201
    assert reindex_response.json()["document_id"] == document_id
    assert delete_response.status_code == 204
    # Reindex while the initial upload job is still queued reuses that job, so
    # only the upload enqueues a worker task.
    assert len(calls) == 1


def test_document_read_exposes_search_version_and_needs_reindex(
    api_client,
    sqlite_session_factory,
) -> None:
    """Version fields are exposed and only indexed legacy docs need reindex."""

    with sqlite_session_factory() as db:
        project = Project(name="versioned")
        db.add(project)
        db.flush()
        project_id = project.id
        legacy = Document(
            project_id=project_id,
            filename="legacy.txt",
            storage_path="/tmp/legacy.txt",
            file_size_bytes=10,
            status=DocumentStatus.indexed,
            search_representation_version="legacy-v0",
        )
        current = Document(
            project_id=project_id,
            filename="current.txt",
            storage_path="/tmp/current.txt",
            file_size_bytes=10,
            status=DocumentStatus.indexed,
            search_representation_version=CURRENT_SEARCH_REPRESENTATION_VERSION,
        )
        pending = Document(
            project_id=project_id,
            filename="pending.txt",
            storage_path="/tmp/pending.txt",
            file_size_bytes=10,
            status=DocumentStatus.uploaded,
            search_representation_version=None,
        )
        db.add_all([legacy, current, pending])
        db.commit()
        legacy_id, current_id, pending_id = legacy.id, current.id, pending.id

    legacy_body = api_client.get(
        f"/api/projects/{project_id}/documents/{legacy_id}"
    ).json()
    current_body = api_client.get(
        f"/api/projects/{project_id}/documents/{current_id}"
    ).json()
    pending_body = api_client.get(
        f"/api/projects/{project_id}/documents/{pending_id}"
    ).json()

    assert legacy_body["search_representation_version"] == "legacy-v0"
    assert legacy_body["needs_reindex"] is True
    assert (
        current_body["search_representation_version"]
        == CURRENT_SEARCH_REPRESENTATION_VERSION
    )
    assert current_body["needs_reindex"] is False
    assert pending_body["search_representation_version"] is None
    assert pending_body["needs_reindex"] is False


def test_reindex_records_current_target_version_without_source_values(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """Reindex queues one job and records only the target version."""

    monkeypatch.setattr(
        "app.services.documents.enqueue_ingestion_job",
        lambda **payload: None,
    )
    with sqlite_session_factory() as db:
        project = Project(name="reindex-version")
        db.add(project)
        db.flush()
        project_id = project.id
        document = Document(
            project_id=project_id,
            filename="legacy.txt",
            storage_path="/tmp/legacy.txt",
            file_size_bytes=10,
            status=DocumentStatus.indexed,
            search_representation_version="legacy-v0",
        )
        db.add(document)
        db.flush()
        document_id = document.id
        db.commit()

    response = api_client.post(
        f"/api/projects/{project_id}/documents/{document_id}/reindex"
    )

    assert response.status_code == 201
    assert response.json()["document_id"] == str(document_id)
    with sqlite_session_factory() as db:
        jobs = db.query(IngestionJob).all()
        metadata = jobs[-1].job_metadata
    assert (
        metadata.get("target_search_representation_version")
        == CURRENT_SEARCH_REPRESENTATION_VERSION
    )
    assert "text" not in metadata
    assert "search_text" not in metadata


def test_repeated_reindex_while_pending_enqueues_once(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """A second reindex while one is queued/running must not enqueue again."""

    calls = []
    monkeypatch.setattr(
        "app.services.documents.enqueue_ingestion_job",
        lambda **payload: calls.append(payload),
    )
    with sqlite_session_factory() as db:
        project = Project(name="idem-reindex")
        db.add(project)
        db.flush()
        project_id = project.id
        document = Document(
            project_id=project_id,
            filename="legacy.txt",
            storage_path="/tmp/legacy.txt",
            file_size_bytes=10,
            status=DocumentStatus.indexed,
            search_representation_version="legacy-v0",
        )
        db.add(document)
        db.flush()
        document_id = document.id
        db.commit()

    first = api_client.post(
        f"/api/projects/{project_id}/documents/{document_id}/reindex"
    )
    second = api_client.post(
        f"/api/projects/{project_id}/documents/{document_id}/reindex"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert len(calls) == 1
    with sqlite_session_factory() as db:
        assert db.query(IngestionJob).count() == 1
        job = db.query(IngestionJob).one()
        assert job.status == "queued"


def test_reindex_after_completed_job_still_enqueues_fresh(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """A completed job must not block a fresh reindex request."""

    from app.models.document import IngestionJobStatus

    calls = []
    monkeypatch.setattr(
        "app.services.documents.enqueue_ingestion_job",
        lambda **payload: calls.append(payload),
    )
    with sqlite_session_factory() as db:
        project = Project(name="completed-reindex")
        db.add(project)
        db.flush()
        project_id = project.id
        document = Document(
            project_id=project_id,
            filename="legacy.txt",
            storage_path="/tmp/legacy.txt",
            file_size_bytes=10,
            status=DocumentStatus.indexed,
            search_representation_version="legacy-v0",
        )
        db.add(document)
        db.flush()
        db.add(
            IngestionJob(
                project_id=project_id,
                document_id=document.id,
                status=IngestionJobStatus.completed,
            )
        )
        document_id = document.id
        db.commit()

    response = api_client.post(
        f"/api/projects/{project_id}/documents/{document_id}/reindex"
    )

    assert response.status_code == 201
    assert len(calls) == 1
    with sqlite_session_factory() as db:
        assert db.query(IngestionJob).count() == 2


@pytest.mark.integration
def test_reindex_request_concurrency_creates_single_job(isolated_database_url) -> None:
    """Concurrent reindex requests for one document create a single queued job."""

    import threading
    import uuid as _uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app.services.documents import request_reindex
    from tests.test_alembic_migration import isolated_database_url_engine

    source_url = make_url(isolated_database_url)
    base_name = source_url.database or "rag"
    database_name = f"{base_name}_test_{_uuid.uuid4().hex[:12]}"
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
                text("INSERT INTO projects (name) VALUES ('conc') RETURNING id")
            ).scalar_one()
            document_id = connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        project_id, filename, storage_path, file_size_bytes,
                        status, source_metadata, search_representation_version
                    )
                    VALUES (:p, 'f.txt', '/tmp/f.txt', 1, 'indexed', '{}'::jsonb,
                            'legacy-v0')
                    RETURNING id
                    """
                ),
                {"p": project_id},
            ).scalar_one()

        from unittest.mock import patch

        barrier = threading.Barrier(2)
        results: list[str] = []

        def _call() -> None:
            from sqlalchemy.orm import Session

            engine = create_engine(test_url)
            with Session(engine) as db:
                barrier.wait()
                try:
                    job = request_reindex(db, project_id, document_id)
                    results.append(str(job.id))
                except Exception as exc:  # pragma: no cover - failure probe
                    results.append(f"error:{type(exc).__name__}")
            engine.dispose()

        with patch(
            "app.services.documents.enqueue_ingestion_job", lambda **kw: None
        ):
            threads = [threading.Thread(target=_call) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        with isolated_database_url_engine(test_url) as connection:
            jobs = connection.execute(
                text(
                    "SELECT count(*) FROM ingestion_jobs WHERE document_id = :d"
                ),
                {"d": document_id},
            ).scalar_one()
            queued = connection.execute(
                text(
                    "SELECT count(*) FROM ingestion_jobs "
                    "WHERE document_id = :d AND status = 'queued'"
                ),
                {"d": document_id},
            ).scalar_one()
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

    assert queued == 1
    assert jobs == 1
    assert all(not result.startswith("error:") for result in results)


@pytest.mark.integration
def test_reindex_job_is_visible_at_dispatch_time(isolated_database_url) -> None:
    """The worker must be able to read the job when dispatch is invoked."""

    import uuid as _uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app.services.documents import request_reindex
    from tests.test_alembic_migration import isolated_database_url_engine

    source_url = make_url(isolated_database_url)
    base_name = source_url.database or "rag"
    database_name = f"{base_name}_test_{_uuid.uuid4().hex[:12]}"
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
                text("INSERT INTO projects (name) VALUES ('vis') RETURNING id")
            ).scalar_one()
            document_id = connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        project_id, filename, storage_path, file_size_bytes,
                        status, source_metadata, search_representation_version
                    )
                    VALUES (:p, 'f.txt', '/tmp/f.txt', 1, 'indexed', '{}'::jsonb,
                            'legacy-v0')
                    RETURNING id
                    """
                ),
                {"p": project_id},
            ).scalar_one()

        from unittest.mock import patch
        from sqlalchemy.orm import Session

        observed: dict = {}

        def enqueue_stub(**payload) -> None:
            engine = create_engine(test_url)
            with Session(engine) as db:
                from app.models.document import IngestionJob as JobModel

                job = db.get(JobModel, _uuid.UUID(payload["job_id"]))
                observed["job_exists"] = job is not None
                observed["job_status"] = job.status.value if job is not None else None
            engine.dispose()

        with patch(
            "app.services.documents.enqueue_ingestion_job", enqueue_stub
        ):
            engine = create_engine(test_url)
            with Session(engine) as db:
                request_reindex(db, project_id, document_id)
            engine.dispose()

        assert observed.get("job_exists") is True
        assert observed.get("job_status") == "queued"
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
