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


def test_table_chunks_repeat_headers_track_ranges_and_keep_global_indices() -> None:
    """Table groups should remain self-contained and follow earlier text chunks."""

    text_section = NormalizedSection(
        section_index=0,
        text="ordinary paragraph",
        source_metadata={"type": "paragraph"},
    )
    table_section = NormalizedSection(
        section_index=1,
        text=(
            "Servers\n"
            "Name | Host\n"
            "app-01 | 10.0.0.1\n"
            "app-02 | 10.0.0.2\n"
            "app-03 | 10.0.0.3\n"
            "app-04 | 10.0.0.4"
        ),
        source_metadata={
            "type": "table",
            "table_index": 0,
            "caption": "Servers",
            "headers": ["Name", "Host"],
            "row_count": 4,
        },
    )

    chunks = chunk_sections(
        uuid.uuid4(),
        uuid.uuid4(),
        [text_section, table_section],
        chunk_size=10,
        chunk_overlap=2,
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    table_chunks = chunks[1:]
    assert [
        (chunk.source_metadata["data_row_start"], chunk.source_metadata["data_row_end"])
        for chunk in table_chunks
    ] == [(1, 2), (3, 4)]
    assert all(chunk.source_metadata["total_rows"] == 4 for chunk in table_chunks)
    assert all(
        chunk.source_metadata["table_chunk_type"] == "table_group"
        for chunk in table_chunks
    )
    assert all(chunk.text.startswith("Servers\nName | Host\n") for chunk in table_chunks)
