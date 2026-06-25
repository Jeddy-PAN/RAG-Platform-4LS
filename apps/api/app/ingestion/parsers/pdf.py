from pathlib import Path

from app.ingestion.parsers.base import ParserError, NormalizedSection


class PdfParser:
    """Parser for PDF page text extracted by PyMuPDF."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        import fitz

        sections: list[NormalizedSection] = []
        with fitz.open(path) as document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                text = page.get_text("text").strip()
                if not text:
                    continue
                sections.append(
                    NormalizedSection(
                        section_index=len(sections),
                        text=text,
                        source_metadata={"page_number": page_index + 1},
                    )
                )

        if not sections:
            raise ParserError("Document contains no usable text")
        return sections
