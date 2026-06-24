import uuid

from app.services.storage import (
    build_storage_path,
    delete_stored_file,
    sanitize_filename,
    write_upload_bytes,
)


def test_sanitize_filename_removes_path_and_unsafe_characters() -> None:
    """Stored filenames should not trust client-provided paths."""

    assert sanitize_filename("../../My File!.pdf") == "My_File_.pdf"
    assert sanitize_filename("   ") == "upload.bin"


def test_storage_path_includes_project_and_document_ids(tmp_path) -> None:
    """Storage paths should make project and document boundaries visible."""

    project_id = uuid.uuid4()
    document_id = uuid.uuid4()

    path = build_storage_path(tmp_path, project_id, document_id, "handbook.pdf")

    assert str(project_id) in str(path)
    assert str(document_id) in str(path)
    assert path.name == "handbook.pdf"


def test_write_and_delete_upload_bytes(tmp_path) -> None:
    """Storage service should write files and ignore missing deletes."""

    path = tmp_path / "project" / "document" / "source.txt"

    write_upload_bytes(path, b"hello")
    assert path.read_bytes() == b"hello"

    delete_stored_file(path)
    delete_stored_file(path)
    assert not path.exists()
