import hashlib
import json
import uuid


CHUNKER_VERSION = "char-word-v1"


def chunk_content_hash(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    text: str,
    source_metadata: dict,
) -> str:
    """Return a stable hash for one chunk candidate."""

    payload = {
        "project_id": str(project_id),
        "document_id": str(document_id),
        "text": text,
        "source_metadata": source_metadata,
        "chunker_version": CHUNKER_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
