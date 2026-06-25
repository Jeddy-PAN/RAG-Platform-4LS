from pathlib import Path

import pytest

from app.ingestion.parsers import get_parser_for_path
from app.ingestion.parsers.base import ParserError


def test_txt_parser_normalizes_utf8_text(tmp_path: Path) -> None:
    """TXT parser should normalize line endings and preserve line metadata."""

    path = tmp_path / "notes.txt"
    path.write_bytes("\ufefffirst line\r\nsecond line\n\n".encode("utf-8"))

    sections = get_parser_for_path(path).parse(path)

    assert len(sections) == 1
    assert sections[0].text == "first line\nsecond line"
    assert sections[0].source_metadata == {"line_start": 1, "line_end": 2}


def test_docx_parser_returns_non_empty_paragraphs(tmp_path: Path) -> None:
    """DOCX parser should extract readable paragraph text."""

    from docx import Document as DocxDocument

    path = tmp_path / "brief.docx"
    document = DocxDocument()
    document.add_paragraph("Alpha paragraph")
    document.add_paragraph("")
    document.add_paragraph("Beta paragraph")
    document.save(path)

    sections = get_parser_for_path(path).parse(path)

    assert [section.text for section in sections] == [
        "Alpha paragraph",
        "Beta paragraph",
    ]
    assert sections[0].source_metadata == {
        "paragraph_start": 1,
        "paragraph_end": 1,
    }


def test_xlsx_parser_returns_visible_sheet_rows(tmp_path: Path) -> None:
    """XLSX parser should convert non-empty rows into deterministic text."""

    from openpyxl import Workbook

    path = tmp_path / "table.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(["Name", "Value"])
    sheet.append(["Alpha", 42])
    workbook.save(path)

    sections = get_parser_for_path(path).parse(path)

    assert [section.text for section in sections] == ["Name | Value", "Alpha | 42"]
    assert sections[1].source_metadata == {
        "sheet_name": "Data",
        "row_start": 2,
        "row_end": 2,
    }


def test_pdf_parser_returns_one_section_per_text_page(tmp_path: Path) -> None:
    """PDF parser should extract text page by page."""

    import fitz

    path = tmp_path / "paper.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "PDF page text")
    pdf.save(path)
    pdf.close()

    sections = get_parser_for_path(path).parse(path)

    assert len(sections) == 1
    assert "PDF page text" in sections[0].text
    assert sections[0].source_metadata == {"page_number": 1}


def test_empty_document_raises_parser_error(tmp_path: Path) -> None:
    """Parsers should fail clearly when no usable text exists."""

    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ParserError, match="no usable text"):
        get_parser_for_path(path).parse(path)
