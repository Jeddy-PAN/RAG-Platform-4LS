import pytest


def create_project(api_client, name: str = "Docs") -> str:
    response = api_client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("source.pdf", "application/pdf"),
        ("source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
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
    assert len(calls) == 2
