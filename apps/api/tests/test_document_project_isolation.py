def test_document_access_requires_matching_project_id(api_client, monkeypatch, tmp_path) -> None:
    """A document UUID from one project must not work under another project."""

    monkeypatch.setattr("app.services.storage.get_upload_root", lambda: tmp_path)
    monkeypatch.setattr("app.services.documents.enqueue_ingestion_job", lambda **payload: None)
    project_a = api_client.post("/api/projects", json={"name": "A"}).json()["id"]
    project_b = api_client.post("/api/projects", json={"name": "B"}).json()["id"]
    document_id = api_client.post(
        f"/api/projects/{project_a}/documents",
        files={"file": ("a.txt", b"alpha", "text/plain")},
    ).json()["document"]["id"]

    get_response = api_client.get(f"/api/projects/{project_b}/documents/{document_id}")
    delete_response = api_client.delete(
        f"/api/projects/{project_b}/documents/{document_id}"
    )
    reindex_response = api_client.post(
        f"/api/projects/{project_b}/documents/{document_id}/reindex"
    )

    assert get_response.status_code == 404
    assert delete_response.status_code == 404
    assert reindex_response.status_code == 404
