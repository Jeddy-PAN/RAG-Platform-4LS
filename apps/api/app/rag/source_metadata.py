"""Public-safe source metadata projection for prompts and citations."""

from collections.abc import Mapping


_PUBLIC_SOURCE_METADATA_KEYS = frozenset(
    {
        "format",
        "type",
        "page_number",
        "heading_path",
        "sheet_name",
        "caption",
        "headers",
        "table_index",
        "block_index",
        "table_range",
        "column_count",
        "row_count",
        "total_rows",
        "data_row",
        "data_row_start",
        "data_row_end",
        "row_start",
        "row_end",
        "sheet_row",
        "paragraph_start",
        "paragraph_end",
    }
)


def public_source_metadata(source_metadata: Mapping | None) -> dict:
    """Return citation-safe location metadata without parser internals."""
    if not source_metadata:
        return {}
    return {
        key: value
        for key, value in source_metadata.items()
        if key in _PUBLIC_SOURCE_METADATA_KEYS
    }
