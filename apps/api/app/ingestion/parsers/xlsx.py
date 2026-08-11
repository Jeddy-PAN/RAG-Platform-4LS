"""Deterministic XLSX worksheet normalization with table provenance."""

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
import re
from typing import Any

from app.ingestion.parsers.base import NormalizedSection, ParserError
from app.ingestion.parsers.docx import _looks_like_header


_DATA_NUMBER = re.compile(
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?"
)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T].*)?")
_IP_ADDRESS = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
_TIME_VALUE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?")
_MACHINE_IDENTIFIER = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\d+"
)


def _looks_like_data_scalar(value: str) -> bool:
    """Return whether a displayed cell value is an unambiguous data scalar."""
    normalized = value.strip()
    return bool(
        _DATA_NUMBER.fullmatch(normalized)
        or _ISO_DATE.fullmatch(normalized)
        or normalized.casefold() in {"true", "false"}
    )


def _looks_like_structured_data_column(values: list[str]) -> bool:
    """Detect repeated identifier/network/time shapes in a data column."""
    values = [value.strip() for value in values if value.strip()]
    if len(values) < 2:
        return False
    if all(_IP_ADDRESS.fullmatch(value) or _TIME_VALUE.fullmatch(value) for value in values):
        return True

    if not all(_MACHINE_IDENTIFIER.fullmatch(value) for value in values):
        return False

    prefix = values[0][:3] if len(values[0]) >= 3 else ""
    return bool(prefix) and sum(value.startswith(prefix) for value in values) >= len(values) * 0.6


@dataclass(frozen=True)
class _Region:
    min_row: int
    max_row: int
    min_col: int
    max_col: int
    table_name: str | None = None
    header_row_count: int = 0

    @property
    def table_range(self) -> str:
        from openpyxl.utils import get_column_letter

        return (
            f"{get_column_letter(self.min_col)}{self.min_row}:"
            f"{get_column_letter(self.max_col)}{self.max_row}"
        )


def _display_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return format(value, "g")
    return str(value).strip()


def _formula_cell(cell: Any) -> bool:
    return getattr(cell, "data_type", None) == "f" or (
        isinstance(getattr(cell, "value", None), str)
        and cell.value.startswith("=")
    )


def _table_ranges(sheet) -> list[_Region]:
    regions: list[_Region] = []
    for table in sheet.tables.values():
        from openpyxl.utils.cell import range_boundaries

        min_col, min_row, max_col, max_row = range_boundaries(table.ref)
        regions.append(
            _Region(
                min_row,
                max_row,
                min_col,
                max_col,
                table.displayName,
                int(getattr(table, "headerRowCount", 1) or 0),
            )
        )
    return regions


def _fallback_regions(occupied: set[tuple[int, int]]) -> list[_Region]:
    if not occupied:
        return []
    rows = sorted({row for row, _ in occupied})
    row_groups: list[list[int]] = []
    current = [rows[0]]
    for row in rows[1:]:
        if row == current[-1] + 1:
            current.append(row)
        else:
            row_groups.append(current)
            current = [row]
    row_groups.append(current)

    regions: list[_Region] = []
    for row_group in row_groups:
        min_row, max_row = row_group[0], row_group[-1]
        columns = sorted({col for row, col in occupied if row in row_group})
        if not columns:
            continue
        segments: list[tuple[int, int]] = []
        start = columns[0]
        for left_col, right_col in zip(columns, columns[1:]):
            gap_width = right_col - left_col - 1
            if gap_width <= 0:
                continue
            left_rows = {
                row for row, col in occupied
                if col <= left_col and row in row_group
            }
            right_rows = {
                row for row, col in occupied
                if col >= right_col and row in row_group
            }
            # Empty columns preserve their positions inside a rectangular
            # table.  Split only when both sides have no occupied row in
            # common, which is evidence that they are independent blocks.
            if left_rows.isdisjoint(right_rows):
                segments.append((start, left_col))
                start = right_col
        segments.append((start, columns[-1]))
        for min_col, max_col in segments:
            segment_rows = sorted(
                row
                for row, col in occupied
                if row in row_group and min_col <= col <= max_col
            )
            regions.append(
                _Region(segment_rows[0], segment_rows[-1], min_col, max_col)
            )
    return regions


def _header_info(rows: list[list[str]], explicit: bool) -> tuple[list[str], float, str, int]:
    if not rows:
        return [], 0.0, "none", 0
    if explicit:
        return rows[0], 0.9, "excel_table", 1
    first = rows[0]
    if first and all(not value or _looks_like_data_scalar(value) for value in first):
        return [], 0.0, "none", 0
    if len(rows) >= 2 and _looks_like_header(first):
        data_rows = rows[1:]
        populated_columns = [
            index
            for index in range(len(first))
            if any(row[index] for row in data_rows if index < len(row))
        ]
        for index in populated_columns:
            column_values = [row[index] for row in data_rows if index < len(row)]
            if _matches_structured_sequence(first[index], column_values):
                return [], 0.0, "none", 0
        first_values = {value.casefold() for value in first if value}
        data_values = {
            value.casefold()
            for row in rows[1:]
            for value in row
            if value
        }
        if first_values and first_values.isdisjoint(data_values):
            return first, 0.75, "heuristic_vocab", 1
        if any(any(char.isdigit() for char in value) for row in rows[1:] for value in row):
            return first, 0.6, "heuristic_pattern", 1
    return [], 0.0, "none", 0


def _matches_structured_sequence(first_value: str, data_values: list[str]) -> bool:
    """Confirm the first cell belongs to the same structured sequence."""
    values = [first_value, *data_values]
    if len(data_values) < 2:
        return False
    if all(
        _looks_like_data_scalar(value)
        or _IP_ADDRESS.fullmatch(value)
        or _TIME_VALUE.fullmatch(value)
        for value in values
    ):
        return True
    return _looks_like_structured_data_column(values)


def _region_cells(sheet, formula_sheet, region: _Region) -> tuple[list[list[str]], list[dict]]:
    rows: list[list[str]] = []
    diagnostics: list[dict] = []
    merged_map: dict[tuple[int, int], tuple[str, str]] = {}
    for merged in sheet.merged_cells.ranges:
        if merged.min_row > region.max_row or merged.max_row < region.min_row:
            continue
        source = sheet.cell(merged.min_row, merged.min_col)
        source_value = _display_value(source.value)
        for row in range(merged.min_row, merged.max_row + 1):
            for col in range(merged.min_col, merged.max_col + 1):
                if (row, col) != (merged.min_row, merged.min_col):
                    merged_map[(row, col)] = (source_value, source.coordinate)

    for row_index in range(region.min_row, region.max_row + 1):
        values: list[str] = []
        formula_addresses: list[str] = []
        merged_sources: dict[str, str] = {}
        formula_count = 0
        unresolved_count = 0
        for col_index in range(region.min_col, region.max_col + 1):
            formula_cell = formula_sheet.cell(row_index, col_index)
            displayed_cell = sheet.cell(row_index, col_index)
            is_formula = _formula_cell(formula_cell)
            if is_formula:
                formula_count += 1
                formula_addresses.append(formula_cell.coordinate)
            value = _display_value(displayed_cell.value)
            if is_formula and not value:
                unresolved_count += 1
            if not value and (row_index, col_index) in merged_map:
                value, source_address = merged_map[(row_index, col_index)]
                merged_sources[displayed_cell.coordinate] = source_address
            values.append(value)
        if any(values) or formula_count:
            rows.append(values)
            diagnostics.append(
                {
                    "sheet_row": row_index,
                    "formula_count": formula_count,
                    "unresolved_formula_count": unresolved_count,
                    "formula_unresolved": unresolved_count > 0,
                    "formula_addresses": sorted(formula_addresses),
                    "merged_sources": merged_sources,
                }
            )
    return rows, diagnostics


def _row_text(values: list[str], headers: list[str]) -> str:
    if headers:
        return " | ".join(
            f"{headers[index]}: {value}" if value and index < len(headers) and headers[index] else value
            for index, value in enumerate(values)
        )
    return " | ".join(values)


def _emit_region(
    sections: list[NormalizedSection],
    sheet,
    formula_sheet,
    region: _Region,
    table_index: int,
    block_index: int,
) -> None:
    rows, diagnostics = _region_cells(sheet, formula_sheet, region)
    if not rows:
        return
    explicit_table = region.table_name is not None
    if explicit_table and region.header_row_count == 0:
        headers, confidence, header_source, header_rows = [], 0.0, "none", 0
    else:
        headers, confidence, header_source, header_rows = _header_info(
            rows, explicit_table
        )
    data_rows = rows[header_rows:]
    data_diagnostics = diagnostics[header_rows:]
    row_count = len(data_rows)
    merged_ranges = [
        str(merged)
        for merged in sheet.merged_cells.ranges
        if merged.min_row <= region.max_row
        and merged.max_row >= region.min_row
        and merged.min_col <= region.max_col
        and merged.max_col >= region.min_col
    ]
    base = {
        "format": "xlsx",
        "sheet_name": sheet.title,
        "table_index": table_index,
        "block_index": block_index,
        "table_range": region.table_range,
        "column_count": region.max_col - region.min_col + 1,
        "row_count": row_count,
        "total_rows": row_count,
        "row_start": region.min_row,
        "row_end": region.max_row,
        "column_start": region.min_col,
        "column_end": region.max_col,
        "headers": headers,
        "header_confidence": confidence,
        "header_source": header_source,
        "merged_ranges": sorted(merged_ranges),
    }
    caption = region.table_name
    if caption:
        base["caption"] = caption
    parts = []
    if caption:
        parts.append(caption)
    if headers:
        parts.append(" | ".join(headers))
    parts.extend(_row_text(row, headers) for row in data_rows)
    sections.append(
        NormalizedSection(len(sections), "\n".join(parts).strip(), {**base, "type": "table", "table_chunk_type": "table"})
    )
    if headers:
        sections.append(
            NormalizedSection(
                len(sections),
                " | ".join(headers),
                {**base, "type": "table_header", "table_chunk_type": "table_header", "row": header_rows - 1, "sheet_row": region.min_row},
            )
        )
    for index, (row, diagnostic) in enumerate(zip(data_rows, data_diagnostics, strict=True), start=1):
        sheet_row = diagnostic["sheet_row"]
        metadata = {
            **base,
            "type": "table_row",
            "table_chunk_type": "table_row",
            "data_row": index,
            "sheet_row": sheet_row,
            "values": row,
            **diagnostic,
        }
        sections.append(NormalizedSection(len(sections), _row_text(row, headers), metadata))


class XlsxParser:
    """Normalize visible XLSX worksheets into table-compatible sections."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        from openpyxl import load_workbook

        try:
            displayed = load_workbook(path, data_only=True, read_only=False)
            formulas = load_workbook(path, data_only=False, read_only=False)
        except Exception as exc:
            raise ParserError("Unable to read XLSX workbook") from exc
        try:
            sections: list[NormalizedSection] = []
            table_index = 0
            for sheet, formula_sheet in zip(displayed.worksheets, formulas.worksheets, strict=True):
                if sheet.sheet_state != "visible":
                    continue
                explicit_regions = _table_ranges(sheet)
                explicit_cells = {
                    (row, col)
                    for region in explicit_regions
                    for row in range(region.min_row, region.max_row + 1)
                    for col in range(region.min_col, region.max_col + 1)
                }
                occupied = set()
                for row in range(1, max(sheet.max_row, formula_sheet.max_row) + 1):
                    for col in range(1, max(sheet.max_column, formula_sheet.max_column) + 1):
                        cell = formula_sheet.cell(row, col)
                        if _formula_cell(cell) or sheet.cell(row, col).value is not None:
                            if (row, col) not in explicit_cells:
                                occupied.add((row, col))
                for merged in sheet.merged_cells.ranges:
                    if any(
                        (row, col) not in explicit_cells
                        for row in range(merged.min_row, merged.max_row + 1)
                        for col in range(merged.min_col, merged.max_col + 1)
                    ):
                        occupied.update(
                            (row, col)
                            for row in range(merged.min_row, merged.max_row + 1)
                            for col in range(merged.min_col, merged.max_col + 1)
                        )
                regions = [*explicit_regions, *_fallback_regions(occupied)]
                regions.sort(key=lambda item: (item.min_row, item.min_col, item.table_name or ""))
                for block_index, region in enumerate(regions):
                    _emit_region(sections, sheet, formula_sheet, region, table_index, block_index)
                    table_index += 1
            if not sections:
                raise ParserError("Document contains no usable text")
            return sections
        finally:
            displayed.close()
            formulas.close()
