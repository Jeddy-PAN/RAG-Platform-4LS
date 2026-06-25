from pathlib import Path

from app.ingestion.parsers.base import ParserError, NormalizedSection


class DocxParser:
    """Parser for DOCX paragraph text."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        from docx import Document

        document = Document(path)
        sections: list[NormalizedSection] = []
        for index, paragraph in enumerate(document.paragraphs, start=1):
            text = paragraph.text.strip()
            if not text:
                continue
            sections.append(
                NormalizedSection(
                    section_index=len(sections),
                    text=text,
                    source_metadata={
                        "paragraph_start": index,
                        "paragraph_end": index,
                    },
                )
            )

        if not sections:
            raise ParserError("Document contains no usable text")
        return sections
