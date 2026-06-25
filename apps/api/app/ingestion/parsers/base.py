from dataclasses import dataclass
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


class DocumentParser(Protocol):
    """Parser interface implemented by each supported file adapter."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        """Parse a document into normalized sections."""
