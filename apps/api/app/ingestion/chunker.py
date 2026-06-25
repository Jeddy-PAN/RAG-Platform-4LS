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
    """Split normalized sections into deterministic word-based chunks."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    candidates: list[ChunkCandidate] = []
    for section in sections:
        words = section.text.split()
        if not words:
            continue
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
                        chunk_index=len(candidates),
                        section_index=section.section_index,
                        text=text,
                        token_count=len(chunk_words),
                        content_hash=chunk_content_hash(
                            project_id,
                            document_id,
                            text,
                            metadata,
                        ),
                        source_metadata=metadata,
                    )
                )
            if start + chunk_size >= len(words):
                break
            start += chunk_size - chunk_overlap
    return candidates
