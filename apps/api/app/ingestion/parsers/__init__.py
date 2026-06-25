from pathlib import Path

from app.ingestion.parsers.base import DocumentParser, ParserError, NormalizedSection
from app.ingestion.parsers.docx import DocxParser
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.parsers.txt import TxtParser
from app.ingestion.parsers.xlsx import XlsxParser


PARSERS_BY_EXTENSION: dict[str, type[DocumentParser]] = {
    ".pdf": PdfParser,
    ".docx": DocxParser,
    ".txt": TxtParser,
    ".xlsx": XlsxParser,
}


def get_parser_for_path(path: Path) -> DocumentParser:
    """Return a parser based on the file extension."""

    parser_class = PARSERS_BY_EXTENSION.get(path.suffix.lower())
    if parser_class is None:
        raise ParserError(f"Unsupported parser extension: {path.suffix.lower() or 'none'}")
    return parser_class()


__all__ = [
    "DocumentParser",
    "NormalizedSection",
    "ParserError",
    "get_parser_for_path",
]
