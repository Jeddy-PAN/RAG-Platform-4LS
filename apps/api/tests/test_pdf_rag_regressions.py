"""Focused retrieval regressions for native-only PDF sections."""

from pathlib import Path
import uuid

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest_document_job
from app.models.document import Document, DocumentSection, DocumentStatus, IngestionJob
from app.models.project import Project
from app.models.retrieval import RetrievalMode
from app.rag.retrieval.service import run_retrieval


class FakeEmbeddingProvider:
    def embed_texts(self, texts):
        return [[0.1] * 1024 for _ in texts]


def _draw_table(
    page,
    top: float,
    rows: list[list[str]],
    header_font: str | None = None,
    header_fill: bool = False,
) -> None:
    left, middle, right = 72, 190, 308
    row_height = 30
    if header_fill:
        page.draw_rect(fitz.Rect(left, top, right, top + row_height), color=None, fill=(0.9, 0.9, 0.9), overlay=False)
    page.draw_rect(fitz.Rect(left, top, right, top + row_height * len(rows)))
    page.draw_line((middle, top), (middle, top + row_height * len(rows)))
    for row_index in range(1, len(rows)):
        y = top + row_height * row_index
        page.draw_line((left, y), (right, y))
    for row_index, row in enumerate(rows):
        fontname = header_font if row_index == 0 and header_font else "helv"
        y = top + 20 + row_index * row_height
        page.insert_text((left + 8, y), row[0], fontname=fontname)
        page.insert_text((middle + 8, y), row[1], fontname=fontname)


def _draw_external_header_table(page, top: float, headers: list[str], rows: list[list[str]]) -> None:
    left, middle, right = 72, 190, 308
    row_height = 30
    page.insert_text((left + 8, top), headers[0])
    page.insert_text((middle + 8, top), headers[1])
    page.draw_rect(fitz.Rect(left, top, right, top + row_height * len(rows)))
    page.draw_line((middle, top), (middle, top + row_height * len(rows)))
    for row_index in range(1, len(rows)):
        y = top + row_height * row_index
        page.draw_line((left, y), (right, y))
    for row_index, row in enumerate(rows):
        y = top + 20 + row_index * row_height
        page.insert_text((left + 8, y), row[0])
        page.insert_text((middle + 8, y), row[1])


def _write_pdf(path: Path, page_two_text: str) -> None:
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "The command result is shown below.")
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), 0)
    pixmap.clear_with(0)
    first.insert_image(fitz.Rect(72, 90, 180, 180), pixmap=pixmap)
    second = document.new_page()
    second.insert_text((72, 72), page_two_text)
    document.save(path)
    document.close()


def _ingest_pdf(db: Session, project: Project, path: Path) -> Document:
    document = Document(
        project_id=project.id,
        filename=path.name,
        storage_path=str(path),
        file_size_bytes=path.stat().st_size,
        status=DocumentStatus.uploaded,
    )
    db.add(document)
    db.flush()
    job = IngestionJob(project_id=project.id, document_id=document.id)
    db.add(job)
    db.commit()
    ingest_document_job(
        db,
        job.id,
        project.id,
        document.id,
        embedding_provider=FakeEmbeddingProvider(),
    )
    return document


def test_pdf_page_search_and_native_figure_text_are_project_scoped(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "alpha.pdf"
    second_path = tmp_path / "other.pdf"
    _write_pdf(first_path, "Alpha evidence is on page two.")
    _write_pdf(second_path, "Other project alpha evidence.")

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name=f"PDF project {uuid.uuid4()}")
        other_project = Project(name=f"PDF other {uuid.uuid4()}")
        db.add_all([project, other_project])
        db.flush()
        _ingest_pdf(db, project, first_path)
        _ingest_pdf(db, other_project, second_path)

        page_result = run_retrieval(
            db,
            project_id=project.id,
            query="Page 2 Alpha evidence",
            mode=RetrievalMode.keyword,
            top_k=4,
        )
        figure_result = run_retrieval(
            db,
            project_id=project.id,
            query="command result below",
            mode=RetrievalMode.keyword,
            top_k=4,
        )

    assert any("Alpha evidence is on page two." in candidate.text for candidate in page_result.results)
    assert all("Other project" not in candidate.text for candidate in page_result.results)
    figure = next(candidate for candidate in figure_result.results if "command result" in candidate.text)
    assert figure.source_metadata["content_role"] == "figure_context"
    assert figure.source_metadata["page_number"] == 1


def test_pdf_external_headers_support_column_retrieval(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    path = tmp_path / "people.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_external_header_table(page, 120, ["Name", "Role"], [["Alice", "Engineer"], ["Bob", "Designer"]])
    document.save(path)
    document.close()

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name=f"PDF table project {uuid.uuid4()}")
        db.add(project)
        db.flush()
        _ingest_pdf(db, project, path)

        result = run_retrieval(
            db,
            project_id=project.id,
            query="Name",
            mode=RetrievalMode.keyword,
            top_k=4,
        )
        full_table_result = run_retrieval(
            db,
            project_id=project.id,
            query="show all rows in Name",
            mode=RetrievalMode.keyword,
            top_k=4,
        )

        stored_table = db.scalar(
            select(DocumentSection).where(
                DocumentSection.project_id == project.id,
                DocumentSection.source_metadata["type"].as_string() == "table",
            )
        )

    header = next(candidate for candidate in result.results if candidate.source_metadata.get("type") == "table_header")
    assert stored_table is not None
    assert stored_table.source_metadata["headers"] == ["Name", "Role"]
    assert header.source_metadata["headers"] == ["Name", "Role"]
    assert header.text == "Name | Role"
    assert full_table_result.table_selection is not None
    assert full_table_result.table_selection.status == "selected"
    assert any("Name: Alice | Role: Engineer" in candidate.text for candidate in full_table_result.results)
    assert any("Name: Bob | Role: Designer" in candidate.text for candidate in full_table_result.results)


def test_pdf_inline_header_candidates_do_not_create_searchable_schema(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    path = tmp_path / "inline-header-candidate.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(
        page,
        100,
        [["Name", "Role"], ["Alice", "Engineer"], ["Bob", "Designer"]],
        header_font="hebo",
        header_fill=True,
    )
    document.save(path)
    document.close()

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name=f"PDF inline candidate {uuid.uuid4()}")
        db.add(project)
        db.flush()
        _ingest_pdf(db, project, path)
        result = run_retrieval(
            db,
            project_id=project.id,
            query="show all rows containing Alice",
            mode=RetrievalMode.keyword,
            top_k=4,
        )

        stored_table = db.scalar(
            select(DocumentSection).where(
                DocumentSection.project_id == project.id,
                DocumentSection.source_metadata["type"].as_string() == "table",
            )
        )

    assert stored_table is not None
    assert stored_table.source_metadata["headers"] == []
    assert "Columns:" not in result.results[0].search_text
    assert not any(candidate.source_metadata.get("type") == "table_header" for candidate in result.results)
    assert any("Name | Role" in candidate.text for candidate in result.results)
    assert any("Alice | Engineer" in candidate.text for candidate in result.results)


def test_pdf_bold_first_data_row_remains_in_full_table_context(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    path = tmp_path / "emphasized-first-record.pdf"
    document = fitz.open()
    page = document.new_page()
    _draw_table(
        page,
        100,
        [["east", "enabled"], ["west", "disabled"], ["north", "standby"]],
        header_font="hebo",
    )
    document.save(path)
    document.close()

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project = Project(name=f"PDF emphasized record {uuid.uuid4()}")
        db.add(project)
        db.flush()
        _ingest_pdf(db, project, path)

        result = run_retrieval(
            db,
            project_id=project.id,
            query="show all rows containing east",
            mode=RetrievalMode.keyword,
            top_k=4,
        )

    assert result.table_selection is not None
    assert result.table_selection.status == "selected"
    assert any("east | enabled" in candidate.text for candidate in result.results), [
        (candidate.source_metadata.get("type"), candidate.text) for candidate in result.results
    ]
    assert any("west | disabled" in candidate.text for candidate in result.results)
    assert any("north | standby" in candidate.text for candidate in result.results)
