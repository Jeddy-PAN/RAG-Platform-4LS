import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageRole
from app.rag.citations import (
    CitationBinding,
    CitationPersistenceError,
    persist_citation_bindings,
)
from app.rag.prompting import PromptSource
from tests.retrieval_test_helpers import seed_retrieval_chunk


def _source(number, chunk):
    return PromptSource(number, chunk.id, chunk.document_id, chunk.document.filename, {}, chunk.text)


def test_persist_citations_links_assistant_message_to_chunks(sqlite_session_factory) -> None:
    """Citations should link assistant messages to same-project chunks."""

    with sqlite_session_factory() as db:
        project, _, chunk = seed_retrieval_chunk(db, "citation", "quoted chunk", [0.1] * 1024)
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(
            project_id=project.id,
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content="Answer",
        )
        db.add(message)
        db.flush()

        citations = persist_citation_bindings(
            db,
            project.id,
            message.id,
            (CitationBinding(1, 1, chunk.id, "quoted chunk"),),
            {1: _source(1, chunk)},
        )

    assert len(citations) == 1
    assert citations[0].chunk_id == chunk.id
    assert citations[0].quote == "quoted chunk"
    assert (citations[0].claim_index, citations[0].source_number) == (1, 1)
    assert (citations[0].quote_start, citations[0].quote_end) == (0, 12)


def test_persist_citations_redacts_internal_metadata(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        project, _, chunk = seed_retrieval_chunk(db, "citation-private", "quoted chunk", [0.1] * 1024)
        chunk.source_metadata = {
            "format": "pdf",
            "page_number": 2,
            "bbox": [1, 2, 3, 4],
            "table_bbox": [5, 6, 7, 8],
            "extraction_confidence": 0.85,
            "sheet_name": "Retained only for cross-format contract",
            "table_index": 0,
            "data_row": 1,
            "header_candidates": ["Name", "Role"],
            "header_candidate_confidence": 0.6,
        }
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(
            project_id=project.id,
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content="Answer",
        )
        db.add(message)
        db.flush()

        citation = persist_citation_bindings(
            db, project.id, message.id,
            (CitationBinding(1, 1, chunk.id, "quoted chunk"),), {1: _source(1, chunk)}
        )[0]

    assert citation.citation_metadata == {
        "format": "pdf",
        "page_number": 2,
        "sheet_name": "Retained only for cross-format contract",
        "table_index": 0,
        "data_row": 1,
    }


def test_cross_project_citation_is_rejected(sqlite_session_factory) -> None:
    """Citation persistence must reject chunks from another project."""

    with Session(sqlite_session_factory.kw["bind"]) as db:
        project, _, _ = seed_retrieval_chunk(db, "a", "a chunk", [0.1] * 1024)
        other_project, _, other_chunk = seed_retrieval_chunk(
            db,
            "b",
            "b chunk",
            [0.1] * 1024,
        )
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(
            project_id=project.id,
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content="Answer",
        )
        db.add(message)
        db.flush()

        with pytest.raises(CitationPersistenceError) as exc:
            persist_citation_bindings(
                db, project.id, message.id,
                (CitationBinding(1, 1, other_chunk.id, "b chunk"),), {1: _source(1, other_chunk)}
            )
        assert exc.value.reason == "project_mismatch"

    assert project.id != other_project.id


def test_persistence_uses_exact_middle_cjk_quote_and_deduplicates_binding(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        project, _, chunk = seed_retrieval_chunk(db, "range", "prefix 中文引用 suffix", [0.1] * 1024)
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(project_id=project.id, conversation_id=conversation.id, role=MessageRole.assistant, content="答案")
        db.add(message)
        db.flush()
        rows = persist_citation_bindings(
            db, project.id, message.id,
            (CitationBinding(1, 1, chunk.id, "中文引用"), CitationBinding(1, 1, chunk.id, "中文引用")),
            {1: _source(1, chunk)},
        )
    assert len(rows) == 1
    assert rows[0].quote_start == len("prefix ")
    assert rows[0].quote == "中文引用"


def test_persistence_rejects_noncontiguous_claim_indexes(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        project, _, chunk = seed_retrieval_chunk(db, "claims", "quoted chunk", [0.1] * 1024)
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(project_id=project.id, conversation_id=conversation.id, role=MessageRole.assistant, content="Answer")
        db.add(message)
        db.flush()
        with pytest.raises(CitationPersistenceError) as exc:
            persist_citation_bindings(
                db, project.id, message.id, (CitationBinding(2, 1, chunk.id, "quoted chunk"),), {1: _source(1, chunk)}
            )
    assert exc.value.reason == "invalid_binding"
