from pathlib import Path
import re

from app.ingestion.parsers.base import ParserError, NormalizedSection
from app.ingestion.parsers.hierarchy import HierarchyState


_ATX_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.*)|[ \t]*)$")
_SETEXT_HEADING = re.compile(r"^(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*((`{3,})|(~{3,}))")


def _atx_heading(line: str) -> tuple[int, str] | None:
    match = _ATX_HEADING.match(line)
    if not match:
        return None
    label = (match.group(2) or "").strip()
    label = re.sub(r"[ \t]+#+[ \t]*$", "", label).strip()
    if not label or re.fullmatch(r"#+", label):
        return None
    return len(match.group(1)), label


def _is_closing_fence(line: str, fence: tuple[str, int]) -> bool:
    """Return whether *line* closes the active Markdown fence."""

    match = _FENCE.match(line)
    if not match:
        return False
    marker = match.group(1)
    return (
        marker[0] == fence[0]
        and len(marker) >= fence[1]
        and not line[match.end() :].strip()
    )


class MarkdownParser:
    """Parser for UTF-8 Markdown files."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        if not any(line.strip() for line in lines):
            raise ParserError("Document contains no usable text")
        sections: list[NormalizedSection] = []
        hierarchy = HierarchyState()
        pending: list[tuple[int, str, bool]] = []
        fence: tuple[str, int] | None = None

        def emit_pending() -> None:
            nonlocal pending
            meaningful = [
                (line_number, line)
                for line_number, line, _ in pending
                if line.strip()
            ]
            if meaningful:
                sections.append(NormalizedSection(
                    len(sections),
                    "\n".join(line for _, line in meaningful).strip(),
                    {
                        "format": "markdown",
                        "line_start": meaningful[0][0],
                        "line_end": meaningful[-1][0],
                        **hierarchy.content_metadata("content"),
                    },
                ))
            pending = []

        def emit_heading(line_number: int, text_value: str, label: str, level: int) -> None:
            sections.append(NormalizedSection(
                len(sections), text_value, {
                    "format": "markdown",
                    "line_start": line_number,
                    "line_end": line_number,
                    **hierarchy.enter_heading(level, label),
                }
            ))

        for line_number, line in enumerate(lines, start=1):
            fence_match = _FENCE.match(line)
            if fence is not None:
                pending.append((line_number, line, False))
                if _is_closing_fence(line, fence):
                    fence = None
                continue
            if fence_match:
                pending.append((line_number, line, False))
                fence = (fence_match.group(1)[0], len(fence_match.group(1)))
                continue

            setext = _SETEXT_HEADING.match(line)
            if setext and pending and pending[-1][2] and pending[-1][1].strip():
                label_line_number, label, _ = pending.pop()
                emit_pending()
                emit_heading(
                    label_line_number,
                    label,
                    label,
                    1 if setext.group(1)[0] == "=" else 2,
                )
                continue

            atx = _atx_heading(line)
            if atx is not None:
                emit_pending()
                emit_heading(line_number, line, atx[1], atx[0])
                continue
            # Empty ATX markers remain content, but cannot become Setext labels.
            pending.append((line_number, line, _ATX_HEADING.match(line) is None))

        emit_pending()
        if not sections:
            raise ParserError("Document contains no usable text")
        return sections
