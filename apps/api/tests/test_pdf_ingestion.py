"""Focused native-only PDF ingestion contracts for Round 5B."""

from pathlib import Path
import uuid

import fitz
import pytest

from app.ingestion.chunker import chunk_sections
from app.ingestion.parsers.base import ParserError
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.search_representation import build_search_text


def _draw_table(
    page,
    top: float,
    rows: list[list[str]],
    header_font: str | None = None,
    header_fill: bool = False,
) -> None:
    left, middle, right = 72, 190, 308
    row_height = 30
    bottom = top + row_height * len(rows)
    if header_fill:
        page.draw_rect(fitz.Rect(left, top, right, top + row_height), color=None, fill=(0.9, 0.9, 0.9), overlay=False)
    page.draw_rect(fitz.Rect(left, top, right, bottom))
    page.draw_line((middle, top), (middle, bottom))
    for row_index in range(1, len(rows)):
        y = top + row_height * row_index
        page.draw_line((left, y), (right, y))
    for row_index, row in enumerate(rows):
        y = top + 20 + row_index * row_height
        fontname = header_font if row_index == 0 and header_font else "helv"
        page.insert_text((left + 8, y), row[0], fontname=fontname)
        if row[1]:
            page.insert_text((middle + 8, y), row[1], fontname=fontname)


def _insert_test_image(page, rect) -> None:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), 0)
    pixmap.clear_with(0)
    page.insert_image(rect, pixmap=pixmap)


def _draw_external_header_table(page, top: float, headers: list[str], rows: list[list[str]]) -> None:
    left, middle, right = 72, 190, 308
    row_height = 30
    page.insert_text((left + 8, top), headers[0])
    page.insert_text((middle + 8, top), headers[1])
    page.draw_rect(fitz.Rect(left, top, right, top + row_height * len(rows)))
    page.draw_line((middle, top), (middle, top + row_height * len(rows)))
    for row_index in range(1, len(rows)):
        y = top + row_height * row_index
        page.draw_line((left, y), (right, y))
    for row_index, row in enumerate(rows):
        y = top + 20 + row_index * row_height
        page.insert_text((left + 8, y), row[0])
        page.insert_text((middle + 8, y), row[1])


def _make_native_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Operations Overview")
    page.insert_text((72, 108), "First native paragraph.")
    _draw_table(page, 150, [["Server", "State"], ["web-01", "active"], ["web-02", ""]])
    page.insert_text((72, 280), "Footer note")
    second = document.new_page()
    second.insert_text((72, 72), "Second page")
    _draw_table(second, 110, [["Service", "Owner"], ["search", "platform"]])
    document.save(path)
    document.close()


def test_pdf_native_blocks_tables_and_chunking_keep_page_provenance(tmp_path: Path) -> None:
    path = tmp_path / "native.pdf"
    _make_native_pdf(path)

    sections = PdfParser().parse(path)
    tables = [section for section in sections if section.source_metadata["type"] == "table"]
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]
    paragraphs = [section for section in sections if section.source_metadata["type"] == "paragraph"]
    chunks = chunk_sections(uuid.uuid4(), uuid.uuid4(), sections, chunk_size=100, chunk_overlap=20)

    assert [paragraph.text for paragraph in paragraphs] == [
        "Operations Overview",
        "First native paragraph.",
        "Footer note",
        "Second page",
    ]
    assert [paragraph.source_metadata["page_block_index"] for paragraph in paragraphs] == [0, 1, 5, 0]
    assert all(paragraph.source_metadata["extraction_method"] == "native_text" for paragraph in paragraphs)
    assert all(paragraph.source_metadata["extraction_confidence"] == 1.0 for paragraph in paragraphs)
    assert all(len(paragraph.source_metadata["bbox"]) == 4 for paragraph in paragraphs)
    assert [table.source_metadata["table_index"] for table in tables] == [0, 1]
    assert [table.source_metadata["page_table_index"] for table in tables] == [0, 0]
    assert tables[0].source_metadata["headers"] == []
    assert tables[0].source_metadata["row_count"] == 3
    assert rows[2].source_metadata["values"] == ["web-02", ""]
    assert rows[2].source_metadata["page_number"] == 1
    assert [row.source_metadata["raw_data_row"] for row in rows[:3]] == [1, 2, 3]
    assert any(chunk.source_metadata.get("type") == "table" for chunk in chunks)


def test_pdf_headerless_tables_keep_all_rows_and_do_not_invent_labels(tmp_path: Path) -> None:
    path = tmp_path / "headerless-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(page, 100, [["web-01", "active"], ["web-02", "down"], ["web-03", "maintenance"]])
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 3
    assert [row.text for row in rows] == ["web-01 | active", "web-02 | down", "web-03 | maintenance"]


def test_pdf_plain_text_headerless_table_keeps_all_rows(tmp_path: Path) -> None:
    path = tmp_path / "plain-text-headerless-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(page, 100, [["east", "enabled"], ["west", "disabled"], ["north", "standby"]])
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 3
    assert [row.text for row in rows] == ["east | enabled", "west | disabled", "north | standby"]


def test_pdf_two_row_plain_text_headerless_table_keeps_both_rows(tmp_path: Path) -> None:
    path = tmp_path / "two-row-plain-text-headerless-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(page, 100, [["east", "enabled"], ["west", "disabled"]])
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 2
    assert [row.text for row in rows] == ["east | enabled", "west | disabled"]


def test_pdf_styled_inline_first_row_remains_a_raw_fact_row(tmp_path: Path) -> None:
    path = tmp_path / "bold-plain-text-header-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(
        page,
        100,
        [["Name", "Role"], ["Alice", "Engineer"], ["Bob", "Designer"]],
        header_font="hebo",
        header_fill=True,
    )
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 3
    assert not any(section.source_metadata["type"] == "table_header" for section in sections)
    assert [row.text for row in rows] == [
        "Name | Role",
        "Alice | Engineer",
        "Bob | Designer",
    ]
    assert [row.source_metadata["raw_data_row"] for row in rows] == [1, 2, 3]
    assert [row.source_metadata["data_row"] for row in rows] == [1, 2, 3]


def test_pdf_external_header_is_the_only_canonical_pdf_schema(tmp_path: Path) -> None:
    path = tmp_path / "external-header-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_external_header_table(page, 120, ["Server", "State"], [["web-01", "active"], ["web-02", "down"]])
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    header = next(section for section in sections if section.source_metadata["type"] == "table_header")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == ["Server", "State"]
    assert table.source_metadata["row_count"] == 2
    assert header.source_metadata["header_origin"] == "external"
    assert [row.text for row in rows] == ["Server: web-01 | State: active", "Server: web-02 | State: down"]
    assert [row.source_metadata["raw_data_row"] for row in rows] == [1, 2]
    assert [row.source_metadata["data_row"] for row in rows] == [1, 2]

    chunks = chunk_sections(uuid.uuid4(), uuid.uuid4(), sections, chunk_size=100, chunk_overlap=20)
    table_chunk = next(chunk for chunk in chunks if chunk.source_metadata.get("table_chunk_type") == "table")
    assert table_chunk.source_metadata["data_row_start"] == 1
    assert table_chunk.source_metadata["data_row_end"] == 2
    assert table_chunk.source_metadata["total_rows"] == 2


def test_pdf_unstyled_plain_text_table_remains_conservatively_headerless(tmp_path: Path) -> None:
    path = tmp_path / "unstyled-plain-text-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(page, 100, [["Name", "Role"], ["Alice", "Engineer"], ["Bob", "Designer"]])
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 3
    assert [row.text for row in rows] == [
        "Name | Role",
        "Alice | Engineer",
        "Bob | Designer",
    ]


def test_pdf_bold_first_plain_text_data_row_remains_headerless(tmp_path: Path) -> None:
    path = tmp_path / "bold-first-data-row-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(
        page,
        100,
        [["east", "enabled"], ["west", "disabled"], ["north", "standby"]],
        header_font="hebo",
    )
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 3
    assert [row.text for row in rows] == ["east | enabled", "west | disabled", "north | standby"]


@pytest.mark.parametrize(
    ("name", "rows"),
    [
        (
            "port-labels",
            [["Port 1", "State"], ["443", "open"], ["8443", "closed"]],
        ),
        (
            "ipv4-labels",
            [["IPv4 Address", "Status"], ["10.0.0.1", "active"], ["10.0.0.2", "down"]],
        ),
    ],
)
def test_pdf_inline_numeric_labels_remain_raw_fact_rows(tmp_path: Path, name: str, rows: list[list[str]]) -> None:
    path = tmp_path / f"{name}.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(page, 100, rows)
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    table = next(section for section in sections if section.source_metadata["type"] == "table")
    data_rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert table.source_metadata["headers"] == []
    assert table.source_metadata["row_count"] == 3
    assert [row.source_metadata["raw_data_row"] for row in data_rows] == [1, 2, 3]
    assert [row.source_metadata["data_row"] for row in data_rows] == [1, 2, 3]


def test_pdf_single_row_headerless_table_emits_a_data_row(tmp_path: Path) -> None:
    path = tmp_path / "single-row-table.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(page, 100, [["web-01", "active"]])
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    rows = [section for section in sections if section.source_metadata["type"] == "table_row"]

    assert len(rows) == 1
    assert rows[0].source_metadata["raw_data_row"] == 1
    assert rows[0].source_metadata["data_row"] == 1
    assert rows[0].text == "web-01 | active"


def test_pdf_figure_context_is_limited_to_adjacent_native_text(tmp_path: Path) -> None:
    path = tmp_path / "figure.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Unrelated introduction")
    page.insert_text((72, 112), "The command result is shown below.")
    _insert_test_image(page, fitz.Rect(72, 130, 220, 230))
    page.insert_text((72, 248), "Figure 1: command output")
    page.insert_text((72, 290), "Ordinary follow-up prose")
    page.insert_text((72, 330), "Restart the service promptly")
    document.save(path)
    document.close()

    sections = PdfParser().parse(path)
    by_text = {section.text: section for section in sections}

    assert by_text["The command result is shown below."].source_metadata["content_role"] == "figure_context"
    assert by_text["Figure 1: command output"].source_metadata["content_role"] == "figure_context"
    assert "content_role" not in by_text["Unrelated introduction"].source_metadata
    assert "content_role" not in by_text["Ordinary follow-up prose"].source_metadata
    assert "content_role" not in by_text["Restart the service promptly"].source_metadata


def test_pdf_short_text_below_image_without_a_cue_is_an_ordinary_paragraph(tmp_path: Path) -> None:
    path = tmp_path / "ordinary-below-image.pdf"
    document = fitz.open()
    page = document.new_page()
    _insert_test_image(page, fitz.Rect(72, 100, 220, 200))
    page.insert_text((72, 220), "Restart the service promptly")
    document.save(path)
    document.close()

    section = PdfParser().parse(path)[0]

    assert section.text == "Restart the service promptly"
    assert "content_role" not in section.source_metadata


def test_image_only_pdf_remains_unsupported_without_ocr(tmp_path: Path) -> None:
    path = tmp_path / "image-only.pdf"
    document = fitz.open()
    page = document.new_page()
    _insert_test_image(page, fitz.Rect(72, 72, 220, 220))
    document.save(path)
    document.close()

    with pytest.raises(ParserError, match="Document contains no usable text"):
        PdfParser().parse(path)


def test_pdf_page_is_searchable_but_geometry_is_not() -> None:
    metadata = {
        "format": "pdf",
        "page_number": 2,
        "bbox": [1, 2, 3, 4],
        "table_bbox": [5, 6, 7, 8],
        "figure_bbox": [9, 10, 11, 12],
        "extraction_method": "native_text",
        "extraction_confidence": 1.0,
    }
    search_text = build_search_text(
        document_name="native.pdf",
        payload_text="The command result is shown below.",
        source_metadata=metadata,
    )

    assert "Page: 2" in search_text
    assert "bbox" not in search_text
    assert "native_text" not in search_text
