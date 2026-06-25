import uuid

from app.ingestion.chunker import chunk_sections
from app.ingestion.parsers.base import NormalizedSection


def test_chunking_is_deterministic_and_applies_overlap() -> None:
    """Chunker should produce stable overlapping chunks."""

    section = NormalizedSection(
        section_index=0,
        text="alpha beta gamma delta epsilon zeta eta theta",
        source_metadata={"page_number": 1},
    )
    project_id = uuid.uuid4()
    document_id = uuid.uuid4()

    first = chunk_sections(project_id, document_id, [section], chunk_size=4, chunk_overlap=2)
    second = chunk_sections(project_id, document_id, [section], chunk_size=4, chunk_overlap=2)

    assert [chunk.text for chunk in first] == [
        "alpha beta gamma delta",
        "gamma delta epsilon zeta",
        "epsilon zeta eta theta",
    ]
    assert [chunk.content_hash for chunk in first] == [
        chunk.content_hash for chunk in second
    ]
    assert first[0].source_metadata["page_number"] == 1
    assert first[0].token_count == 4


def test_tiny_text_returns_one_chunk() -> None:
    """Text shorter than chunk_size should still produce one chunk."""

    section = NormalizedSection(section_index=0, text="short text", source_metadata={})

    chunks = chunk_sections(uuid.uuid4(), uuid.uuid4(), [section])

    assert len(chunks) == 1
    assert chunks[0].text == "short text"
