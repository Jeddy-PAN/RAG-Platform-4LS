"""Contract tests for the Round 2 canonical search-text builder."""

from app.ingestion.search_representation import (
    CURRENT_SEARCH_REPRESENTATION_VERSION,
    build_search_text,
)


def test_hierarchy_context_uses_current_v3_representation_and_redacts_identity():
    output = _build(
        document_name="runbook.md",
        payload_text="restart service",
        source_metadata={
            "heading_path": "Operations > Production",
            "structural_parent_id": "h:1/secret",
            "heading_level": 2,
            "line_start": 9,
        },
    )

    assert CURRENT_SEARCH_REPRESENTATION_VERSION == "canonical-search-v3"
    assert "Heading: Operations > Production" in output
    assert "secret" not in output
    assert "heading_level" not in output
    assert "line_start" not in output


def _build(
    *,
    document_name: str,
    payload_text: str,
    source_metadata: dict | None = None,
) -> str:
    return build_search_text(
        document_name=document_name,
        payload_text=payload_text,
        source_metadata=source_metadata or {},
    )


def test_output_is_deterministic() -> None:
    """Identical inputs must produce byte-identical output."""

    first = _build(
        document_name="systems.docx",
        payload_text="ServerName: node-01",
        source_metadata={"headers": ["ServerName"]},
    )
    second = _build(
        document_name="systems.docx",
        payload_text="ServerName: node-01",
        source_metadata={"headers": ["ServerName"]},
    )
    assert first == second


def test_ordinary_paragraph_includes_document_and_payload() -> None:
    """Plain paragraph output stays understandable and retains the payload."""

    output = _build(
        document_name="handbook.pdf",
        payload_text="Escalation starts after triage.",
        source_metadata={"page_number": 4},
    )
    assert "Document: handbook.pdf" in output
    assert "Content:" in output
    assert "Escalation starts after triage." in output


def test_pdf_page_number_is_allowlisted_but_other_formats_remain_unchanged() -> None:
    pdf = _build(
        document_name="handbook.pdf",
        payload_text="Escalation starts after triage.",
        source_metadata={"format": "pdf", "page_number": 4},
    )
    xlsx = _build(
        document_name="inventory.xlsx",
        payload_text="node-01",
        source_metadata={"format": "xlsx", "page_number": 4},
    )

    assert "Page: 4" in pdf
    assert "Page:" not in xlsx


def test_field_ordering_follows_the_fixed_contract() -> None:
    """Filename, sheet, caption, headers, then payload appear in that order."""

    output = _build(
        document_name="monitor.xlsx",
        payload_text="row-value-1 | row-value-2",
        source_metadata={
            "sheet_name": "Inventory",
            "caption": "Production Login",
            "headers": ["Server", "Username"],
        },
    )
    doc_pos = output.index("Document: monitor.xlsx")
    sheet_pos = output.index("Sheet: Inventory")
    table_pos = output.index("Table: Production Login")
    columns_pos = output.index("Columns: Server | Username")
    content_pos = output.index("Content:")
    assert doc_pos < sheet_pos < table_pos < columns_pos < content_pos


def test_empty_and_null_metadata_values_are_skipped() -> None:
    """Blank or missing sheet/caption/headers must not emit empty lines."""

    output = _build(
        document_name="plain.txt",
        payload_text="A single line.",
        source_metadata={
            "sheet_name": "",
            "caption": None,
            "headers": [],
            "heading_path": "  ",
        },
    )
    assert "Sheet:" not in output
    assert "Table:" not in output
    assert "Columns:" not in output
    assert "Heading:" not in output
    assert "A single line." in output


def test_arbitrary_metadata_and_storage_paths_are_excluded() -> None:
    """Only allowlisted retrieval context may enter search text."""

    output = _build(
        document_name="secret.docx",
        payload_text="payload row",
        source_metadata={
            "storage_path": "/var/data/uploads/secret.docx",
            "content_hash": "abc123",
            "chunker_version": "v1",
            "job_id": "job-1",
            "page_number": 9,
            "data_row": 3,
            "embedding_norm": 0.5,
        },
    )
    assert "/var/data/uploads" not in output
    assert "abc123" not in output
    assert "chunker_version" not in output
    assert "job-1" not in output
    assert "payload row" in output


def test_input_metadata_is_not_mutated() -> None:
    """The builder must not modify the caller's metadata dict."""

    metadata = {"headers": ["Server"], "caption": "Login"}
    before = dict(metadata)
    _build(document_name="file.docx", payload_text="row", source_metadata=metadata)
    assert metadata == before


def test_identical_context_line_present_in_payload_is_not_duplicated() -> None:
    """A caption already present as a payload line must not be repeated."""

    payload = "Production Login\nServer | Username\nnode-01 | operator"
    output = _build(
        document_name="login.docx",
        payload_text=payload,
        source_metadata={"caption": "Production Login", "headers": ["Server", "Username"]},
    )
    assert output.count("Production Login") == 1
    # The header line is also present in the payload, so no Columns: label.
    assert "Columns:" not in output


def test_headerless_table_does_not_gain_factual_headers() -> None:
    """No headers metadata means no invented Columns line."""

    output = _build(
        document_name="table.docx",
        payload_text="alpha\nbeta",
        source_metadata={"caption": None, "headers": []},
    )
    assert "Columns:" not in output
    assert "alpha" in output


def test_headers_are_joined_and_preserved() -> None:
    """Header labels join with a stable separator and keep original case."""

    output = _build(
        document_name="acc.docx",
        payload_text="operator | admin",
        source_metadata={"headers": ["ServerName", "Role"]},
    )
    assert "Columns: ServerName | Role" in output


def test_identifier_case_and_value_are_preserved() -> None:
    """Identifiers like node-01 keep their original case and separators."""

    payload = "ServerName: node-01 | Username: Operator"
    output = _build(document_name="systems.docx", payload_text=payload)
    assert "node-01" in output
    assert "Operator" in output


def test_non_empty_payload_never_returns_empty() -> None:
    """With a non-empty payload the builder always returns non-empty text."""

    output = _build(
        document_name="",
        payload_text="only content matters",
        source_metadata={"caption": "", "headers": []},
    )
    assert output.strip()
    assert "only content matters" in output
