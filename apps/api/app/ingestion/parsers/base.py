from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class ParserError(RuntimeError):
    """Raised when a document cannot produce usable text sections."""


@dataclass(frozen=True)
class NormalizedSection:
    """Parser-neutral section text with source location metadata."""

    section_index: int
    text: str
    source_metadata: dict


@dataclass(frozen=True)
class StructuredTable:
    """Shared structured-table representation for DOCX, XLSX, and PDF parsers.

    Parsers normalise their native table structures into this contract so that
    section-emitting code and table-aware chunking can work across all formats.

    Column positions are preserved: every row list has the same length as
    ``column_count``, with empty cells stored as empty strings.
    """

    table_index: int
    block_index: int = 0
    caption: str | None = None
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    column_count: int = 0
    header_confidence: float = 0.0
    source_metadata: dict = field(default_factory=dict)


class DocumentParser(Protocol):
    """Parser interface implemented by each supported file adapter."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        """Parse a document into normalized sections."""
