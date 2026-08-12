"""Native-text PDF normalization with page, table, and figure provenance."""

from dataclasses import dataclass
from pathlib import Path
import re

from app.ingestion.parsers.base import NormalizedSection, ParserError


_FIGURE_CUES = ("below", "following", "above", "figure", "screenshot", "output", "result")
_FIGURE_GAP = 72.0


@dataclass(frozen=True)
class _TextBlock:
    index: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class _NativeTable:
    bbox: tuple[float, float, float, float]
    raw_rows: list[list[str]]
    headers: list[str]
    header_confidence: float
    header_source: str
    header_candidates: list[str]
    header_candidate_confidence: float


def _rect_area(rect: tuple[float, float, float, float]) -> float:
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _mostly_inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
    x0, y0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    x1, y1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    return _rect_area((x0, y0, x1, y1)) >= _rect_area(inner) * 0.8


def _normalized_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        text = "".join(span.get("text", "") for span in line.get("spans", []))
        if text.strip():
            lines.append(text.strip())
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _text_blocks(page) -> list[_TextBlock]:
    blocks: list[_TextBlock] = []
    for block_index, block in enumerate(page.get_text("dict", sort=True).get("blocks", [])):
        if block.get("type") != 0:
            continue
        text = _normalized_text(block)
        if not text:
            continue
        bbox = tuple(float(value) for value in block["bbox"])
        blocks.append(_TextBlock(block_index, text, bbox))
    return blocks


def _native_tables(page) -> list[_NativeTable]:
    if not hasattr(page, "find_tables"):
        return []
    try:
        found = page.find_tables()
    except Exception:
        return []

    normalized: list[_NativeTable] = []
    for table in found.tables:
        try:
            raw_rows = [[str(cell).strip() if cell is not None else "" for cell in row] for row in table.extract()]
            if not raw_rows:
                continue
            column_count = len(raw_rows[0])
            if not column_count or any(len(row) != column_count for row in raw_rows):
                continue
            extracted_headers = [str(value).strip() if value else "" for value in table.header.names]
            if getattr(table.header, "external", False) and extracted_headers and len(extracted_headers) == column_count:
                headers = extracted_headers
                header_confidence, header_source = 0.9, "pymupdf_header"
            else:
                headers = []
                header_confidence, header_source = 0.0, "none"
            normalized.append(
                _NativeTable(
                    tuple(float(value) for value in table.bbox),
                    raw_rows,
                    headers,
                    header_confidence,
                    header_source,
                    raw_rows[0] if len(raw_rows) >= 2 else [],
                    0.0,
                )
            )
        except Exception:
            continue
    return normalized


def _image_rectangles(page) -> list[tuple[float, float, float, float]]:
    rectangles: list[tuple[float, float, float, float]] = []
    for image in page.get_images(full=True):
        try:
            for rect in page.get_image_rects(image[0]):
                rectangles.append(tuple(float(value) for value in rect))
        except Exception:
            continue
    return rectangles


def _horizontal_overlap(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return min(first[2], second[2]) > max(first[0], second[0])


def _figure_context_indexes(
    blocks: list[_TextBlock],
    tables: list[_NativeTable],
    image_rectangles: list[tuple[float, float, float, float]],
) -> dict[int, tuple[int, tuple[float, float, float, float]]]:
    qualifying: dict[int, tuple[int, tuple[float, float, float, float]]] = {}
    usable = [block for block in blocks if not any(_mostly_inside(block.bbox, table.bbox) for table in tables)]
    for image_index, image_bbox in enumerate(image_rectangles):
        below = []
        for block in usable:
            if not _horizontal_overlap(block.bbox, image_bbox):
                continue
            text_lower = block.text.casefold()
            has_cue = any(cue in text_lower for cue in _FIGURE_CUES)
            above_gap = image_bbox[1] - block.bbox[3]
            below_gap = block.bbox[1] - image_bbox[3]
            if 0 <= above_gap <= _FIGURE_GAP and has_cue:
                qualifying[block.index] = (image_index, image_bbox)
            elif 0 <= below_gap <= _FIGURE_GAP:
                below.append((below_gap, block, has_cue))
        if below:
            _, block, has_cue = min(below, key=lambda candidate: candidate[0])
            if has_cue:
                qualifying[block.index] = (image_index, image_bbox)
    return qualifying


def _row_text(values: list[str], headers: list[str]) -> str:
    if not headers:
        return " | ".join(values)
    return " | ".join(
        f"{headers[index]}: {value}" if value and headers[index] else value
        for index, value in enumerate(values)
    )


def _emit_table(
    sections: list[NormalizedSection],
    table: _NativeTable,
    *,
    page_number: int,
    page_table_index: int,
    table_index: int,
    block_index: int,
) -> None:
    base = {
        "format": "pdf",
        "type": "table",
        "page_number": page_number,
        "page_table_index": page_table_index,
        "table_index": table_index,
        "block_index": block_index,
        "bbox": list(table.bbox),
        "table_bbox": list(table.bbox),
        "column_count": len(table.raw_rows[0]) if table.raw_rows else len(table.headers),
        "row_count": len(table.raw_rows),
        "total_rows": len(table.raw_rows),
        "headers": table.headers,
        "header_confidence": table.header_confidence,
        "header_source": table.header_source,
        "header_candidates": table.header_candidates,
        "header_candidate_confidence": table.header_candidate_confidence,
        "extraction_method": "native_table",
        "extraction_confidence": 0.85,
        "table_chunk_type": "table",
    }
    parts = []
    if table.headers:
        parts.append(" | ".join(table.headers))
    parts.extend(_row_text(row, table.headers) for row in table.raw_rows)
    sections.append(NormalizedSection(len(sections), "\n".join(parts).strip(), base))
    if table.headers:
        sections.append(
            NormalizedSection(
                len(sections),
                " | ".join(table.headers),
                {
                    **base,
                    "type": "table_header",
                    "table_chunk_type": "table_header",
                    "row": 0,
                    "header_origin": "external",
                },
            )
        )
    for raw_data_row, values in enumerate(table.raw_rows, start=1):
        sections.append(
            NormalizedSection(
                len(sections),
                _row_text(values, table.headers),
                {
                    **base,
                    "type": "table_row",
                    "table_chunk_type": "table_row",
                    "raw_data_row": raw_data_row,
                    "data_row": raw_data_row,
                    "values": values,
                },
            )
        )


class PdfParser:
    """Normalize PDF native text, native tables, and conservative figure context."""

    def parse(self, path: Path) -> list[NormalizedSection]:
        import fitz

        try:
            document = fitz.open(path)
        except Exception as exc:
            raise ParserError("Unable to read PDF document") from exc
        try:
            sections: list[NormalizedSection] = []
            table_index = 0
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1
                tables = _native_tables(page)
                blocks = _text_blocks(page)
                figure_context = _figure_context_indexes(blocks, tables, _image_rectangles(page))
                elements: list[tuple[float, float, str, object]] = []
                for table_position, table in enumerate(tables):
                    elements.append((table.bbox[1], table.bbox[0], "table", (table_position, table)))
                for block in blocks:
                    if not any(_mostly_inside(block.bbox, table.bbox) for table in tables):
                        elements.append((block.bbox[1], block.bbox[0], "paragraph", block))
                for block_index, (_, _, kind, value) in enumerate(sorted(elements, key=lambda item: item[:2])):
                    if kind == "table":
                        page_table_index, table = value
                        _emit_table(
                            sections,
                            table,
                            page_number=page_number,
                            page_table_index=page_table_index,
                            table_index=table_index,
                            block_index=block_index,
                        )
                        table_index += 1
                        continue
                    block = value
                    metadata = {
                        "format": "pdf",
                        "type": "paragraph",
                        "page_number": page_number,
                        "page_block_index": block.index,
                        "block_index": block_index,
                        "bbox": list(block.bbox),
                        "extraction_method": "native_text",
                        "extraction_confidence": 1.0,
                    }
                    if block.index in figure_context:
                        figure_index, figure_bbox = figure_context[block.index]
                        metadata.update(
                            {
                                "content_role": "figure_context",
                                "figure_index": figure_index,
                                "figure_bbox": list(figure_bbox),
                            }
                        )
                    sections.append(NormalizedSection(len(sections), block.text, metadata))
            if not sections:
                raise ParserError("Document contains no usable text")
            return sections
        finally:
            document.close()
