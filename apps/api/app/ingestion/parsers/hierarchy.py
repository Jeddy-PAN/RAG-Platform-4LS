"""Parser-neutral document heading hierarchy state."""

from dataclasses import dataclass
import re
from urllib.parse import quote


def normalize_heading_label(label: str) -> str:
    """Collapse whitespace in a heading label without changing its content."""

    return re.sub(r"\s+", " ", label).strip()


@dataclass(frozen=True)
class HeadingEntry:
    level: int
    label: str
    occurrence: int
    segment: str


class HierarchyState:
    """Maintain deterministic active heading ancestry for one document."""

    def __init__(self) -> None:
        self._entries: list[HeadingEntry] = []
        self._occurrences: dict[tuple[tuple[str, ...], int, str], int] = {}

    def enter_heading(self, level: int, label: str) -> dict:
        if not 1 <= level <= 9:
            raise ValueError("heading level must be between 1 and 9")
        normalized = normalize_heading_label(label)
        if not normalized:
            raise ValueError("heading label must not be empty")

        self._entries = [entry for entry in self._entries if entry.level < level]
        parent_segments = tuple(entry.segment for entry in self._entries)
        occurrence_key = (parent_segments, level, normalized)
        occurrence = self._occurrences.get(occurrence_key, 0) + 1
        self._occurrences[occurrence_key] = occurrence
        encoded = quote(normalized, safe="")
        suffix = "" if occurrence == 1 else f"#{occurrence}"
        entry = HeadingEntry(level, normalized, occurrence, f"h:{level}/{encoded}{suffix}")
        self._entries.append(entry)
        return {
            **self._active_metadata(),
            "heading_level": level,
            "section_role": "heading",
        }

    def content_metadata(self, role: str) -> dict:
        if role not in {"content", "table"}:
            raise ValueError("content role must be 'content' or 'table'")
        return {**self._active_metadata(), "section_role": role}

    def _active_metadata(self) -> dict:
        if not self._entries:
            return {}
        return {
            "heading_path": " > ".join(entry.label for entry in self._entries),
            "structural_parent_id": "/".join(entry.segment for entry in self._entries),
        }
