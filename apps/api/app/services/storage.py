from pathlib import Path
import re
import uuid

from app.core.config import get_settings


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx"}


def get_upload_root() -> Path:
    """Return the configured local upload root."""

    return Path(get_settings().upload_storage_dir)


def sanitize_filename(filename: str) -> str:
    """Return a safe basename for local file storage."""

    basename = Path(filename.strip()).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", basename).strip("._")
    return safe_name or "upload.bin"


def get_supported_extension(filename: str) -> str:
    """Validate and return the lower-case supported file extension."""

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension or 'none'}")
    return extension


def build_storage_path(
    root: Path,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    safe_filename: str,
) -> Path:
    """Build the project/document scoped storage path."""

    return root / str(project_id) / str(document_id) / safe_filename


def write_upload_bytes(path: Path, content: bytes) -> None:
    """Write uploaded bytes to the local storage path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def delete_stored_file(path: str | Path) -> None:
    """Delete a stored file while ignoring already-missing paths."""

    Path(path).unlink(missing_ok=True)
