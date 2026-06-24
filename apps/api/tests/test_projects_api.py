def test_create_list_get_update_and_delete_project(api_client) -> None:
    """Project CRUD endpoints should manage knowledge-base containers."""

    create_response = api_client.post(
        "/api/projects",
        json={"name": "Client Research", "description": "Planning docs"},
    )
    assert create_response.status_code == 201
    project = create_response.json()

    list_response = api_client.get("/api/projects")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [project["id"]]

    get_response = api_client.get(f"/api/projects/{project['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Client Research"

    update_response = api_client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Client Research Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Client Research Updated"

    delete_response = api_client.delete(f"/api/projects/{project['id']}")
    assert delete_response.status_code == 204

    missing_response = api_client.get(f"/api/projects/{project['id']}")
    assert missing_response.status_code == 404


def test_duplicate_project_name_returns_409(api_client) -> None:
    """Project names are unique so the sidebar stays unambiguous."""

    first = api_client.post("/api/projects", json={"name": "Duplicate"})
    second = api_client.post("/api/projects", json={"name": "Duplicate"})

    assert first.status_code == 201
    assert second.status_code == 409


def test_missing_project_returns_404(api_client) -> None:
    """Unknown project IDs should produce predictable 404 responses."""

    response = api_client.get("/api/projects/00000000-0000-0000-0000-000000000001")

    assert response.status_code == 404
