from dataclasses import dataclass
import uuid

from app.ingestion.hashing import CHUNKER_VERSION, chunk_content_hash
from app.ingestion.parsers.base import NormalizedSection


@dataclass(frozen=True)
class ChunkCandidate:
    """Chunk ready to be embedded and written to the database."""

    chunk_index: int
    section_index: int
    text: str
    token_count: int
    content_hash: str
    source_metadata: dict


def chunk_sections(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    sections: list[NormalizedSection],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[ChunkCandidate]:
    """Split normalized sections into deterministic chunks.

    Table sections (``source_metadata["type"] == "table"``) are split by
    line so that row boundaries are preserved.  All other sections use
    word-based sliding-window chunking.

    Chunk indices are globally unique and sequential within a document
    (``0..N-1``), regardless of how many sections are processed.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    candidates: list[ChunkCandidate] = []
    for section in sections:
        is_table = section.source_metadata.get("type") == "table"
        offset = len(candidates)
        if is_table:
            new_chunks = _chunk_table_section(
                project_id, document_id, section, chunk_size, offset
            )
        else:
            new_chunks = _chunk_text_section(
                project_id, document_id, section, chunk_size, chunk_overlap, offset
            )
        candidates.extend(new_chunks)
    return candidates


def _chunk_table_section(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    section: NormalizedSection,
    chunk_size: int,
    global_offset: int,
) -> list[ChunkCandidate]:
    """Split a table section into row-group chunks.

    Each group repeats the caption and column headers so that every
    group is independently understandable.  Data-row ranges use 1-based
    inclusive ``data_row_start`` / ``data_row_end``.
    """
    # Parse structure from parser-produced metadata
    caption = section.source_metadata.get("caption")
    headers: list[str] = section.source_metadata.get("headers", [])
    header_text = " | ".join(h for h in headers if h) if headers else ""
    total_rows: int = section.source_metadata.get("row_count", 0)

    # Separate caption and header lines from data lines
    full_text = section.text
    lines = full_text.split("\n")

    # Re-parse: first non-empty line after caption is the header line
    data_lines: list[str] = []
    caption_line: str | None = None
    header_line_idx: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if caption and stripped == caption and caption_line is None:
            caption_line = stripped
        elif header_text and stripped == header_text and header_line_idx is None:
            header_line_idx = i
        else:
            data_lines.append(stripped)

    if not data_lines:
        # Edge case: table with caption/header but no data rows in this section
        # (should not happen with current parser but be defensive)
        text = full_text.strip()
        if text:
            metadata = _build_metadata(section, global_offset, 0, 0, total_rows)
            return [
                ChunkCandidate(
                    chunk_index=global_offset,
                    section_index=section.section_index,
                    text=text,
                    token_count=len(text.split()),
                    content_hash=chunk_content_hash(project_id, document_id, text, metadata),
                    source_metadata=metadata,
                )
            ]
        return []

    candidates: list[ChunkCandidate] = []
    start = 0
    while start < len(data_lines):
        word_count = 0
        # Prepend caption + header overhead for each group
        overhead = len(header_text.split()) if header_text else 0
        if caption:
            overhead += len(caption.split())

        end = start
        while end < len(data_lines):
            line_words = len(data_lines[end].split())
            if word_count + line_words + overhead > chunk_size and end > start:
                break
            word_count += line_words
            end += 1

        # Build group text with caption and headers
        parts: list[str] = []
        if caption and caption_line:
            parts.append(caption_line)
        if header_text:
            parts.append(header_text)
        parts.extend(data_lines[start:end])

        chunk_text = "\n".join(parts).strip()
        if chunk_text:
            # 1-based inclusive data row range
            data_row_start = start + 1
            data_row_end = end  # inclusive

            metadata = _build_metadata(
                section,
                global_offset + len(candidates),
                data_row_start,
                data_row_end,
                total_rows,
            )
            candidates.append(
                ChunkCandidate(
                    chunk_index=global_offset + len(candidates),
                    section_index=section.section_index,
                    text=chunk_text,
                    token_count=word_count + overhead,
                    content_hash=chunk_content_hash(project_id, document_id, chunk_text, metadata),
                    source_metadata=metadata,
                )
            )
        start = end
    return candidates


def _build_metadata(
    section: NormalizedSection,
    chunk_idx: int,
    data_row_start: int,
    data_row_end: int,
    total_rows: int,
) -> dict:
    """Build consistent chunk metadata with table-aware fields.

    ``table_chunk_type`` follows the contract:
    - ``"table"`` — complete small table (covers all rows)
    - ``"table_group"`` — contiguous segment of a large table
    """
    is_complete = (
        total_rows > 0
        and data_row_start == 1
        and data_row_end == total_rows
    )
    return {
        **section.source_metadata,
        "section_index": section.section_index,
        "chunker_version": CHUNKER_VERSION,
        "chunk_index": chunk_idx,
        "data_row_start": data_row_start,
        "data_row_end": data_row_end,
        "total_rows": total_rows,
        "table_chunk_type": "table" if is_complete else "table_group",
    }


def _chunk_text_section(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    section: NormalizedSection,
    chunk_size: int,
    chunk_overlap: int,
    global_offset: int,
) -> list[ChunkCandidate]:
    """Split a non-table section using word-based sliding-window chunking."""
    words = section.text.split()
    if not words:
        return []

    candidates: list[ChunkCandidate] = []
    start = 0
    while start < len(words):
        chunk_words = words[start : start + chunk_size]
        text = " ".join(chunk_words).strip()
        if text:
            metadata = {
                **section.source_metadata,
                "section_index": section.section_index,
                "chunker_version": CHUNKER_VERSION,
            }
            candidates.append(
                ChunkCandidate(
                    chunk_index=global_offset + len(candidates),
                    section_index=section.section_index,
                    text=text,
                    token_count=len(chunk_words),
                    content_hash=chunk_content_hash(project_id, document_id, text, metadata),
                    source_metadata=metadata,
                )
            )
        if start + chunk_size >= len(words):
            break
        start += chunk_size - chunk_overlap
    return candidates
