from pathlib import Path

from app.ingestion.parsers.base import ParserError, NormalizedSection


class TxtParser:
    """Parser for UTF-8 plain text files."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        non_empty = [(index + 1, line) for index, line in enumerate(lines) if line.strip()]
        if not non_empty:
            raise ParserError("Document contains no usable text")

        return [
            NormalizedSection(
                section_index=0,
                text="\n".join(line for _, line in non_empty).strip(),
                source_metadata={
                    "line_start": non_empty[0][0],
                    "line_end": non_empty[-1][0],
                },
            )
        ]
