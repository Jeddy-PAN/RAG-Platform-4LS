"""Canonical search representation and its deterministic builder.

Round 2 separates the text used to find a chunk from the original payload
supplied to the LLM. ``search_text`` decides whether a chunk is found; the
original chunk ``text`` decides what factual content the model may answer from.
"""

import re
from collections.abc import Mapping


LEGACY_SEARCH_REPRESENTATION_VERSION = "legacy-v0"
CURRENT_SEARCH_REPRESENTATION_VERSION = "canonical-search-v3"


def _normalize(value: str) -> str:
    """Collapse repeated whitespace and trim the value."""

    return re.sub(r"[ \t]+", " ", value.strip())


def _context_entries(
    document_name: str,
    source_metadata: Mapping,
) -> list[tuple[str, str]]:
    """Return ``(label, value)`` context pairs in the fixed contract order.

    Only an allowlist of retrieval context enters search text. UUIDs, storage
    paths, hashes, page/row numbers, parser diagnostics, and confidence values
    are never serialized.
    """
    entries: list[tuple[str, str]] = []

    name = _normalize(document_name)
    if name:
        entries.append(("Document", name))

    page_number = source_metadata.get("page_number")
    if source_metadata.get("format") == "pdf" and isinstance(page_number, int) and page_number > 0:
        entries.append(("Page", str(page_number)))

    heading_path = source_metadata.get("heading_path")
    if isinstance(heading_path, str) and heading_path.strip():
        entries.append(("Heading", _normalize(heading_path)))

    sheet_name = source_metadata.get("sheet_name")
    if isinstance(sheet_name, str) and sheet_name.strip():
        entries.append(("Sheet", _normalize(sheet_name)))

    caption = source_metadata.get("caption")
    if isinstance(caption, str) and caption.strip():
        entries.append(("Table", _normalize(caption)))

    headers = source_metadata.get("headers")
    if isinstance(headers, list):
        cleaned = [
            _normalize(header)
            for header in headers
            if isinstance(header, str) and header.strip()
        ]
        if cleaned:
            entries.append(("Columns", " | ".join(cleaned)))

    return entries


def build_search_text(
    *,
    document_name: str,
    payload_text: str,
    source_metadata: dict,
) -> str:
    """Build a deterministic search representation from an allowlist of context.

    The output is stable, does not mutate ``source_metadata``, preserves
    identifier case, and never returns empty text when ``payload_text`` is
    non-empty. A context line that is already present in the payload is not
    repeated.
    """
    payload = payload_text.strip() if payload_text else ""
    payload_lines = [line.strip() for line in payload.splitlines() if line.strip()]

    lines: list[str] = []
    for label, value in _context_entries(document_name, source_metadata):
        # XLSX table headers are structural context even when the chunk
        # payload repeats the header line for table chunking.
        if value in payload_lines and not (
            label == "Columns" and source_metadata.get("format") == "xlsx"
        ):
            continue
        lines.append(f"{label}: {value}")

    if payload:
        lines.append("Content:")
        lines.append(payload)

    return "\n".join(lines).strip()
