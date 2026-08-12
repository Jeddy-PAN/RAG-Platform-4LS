import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageRole
from app.rag.citations import persist_citations
from tests.retrieval_test_helpers import seed_retrieval_chunk


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

        citations = persist_citations(
            db,
            project.id,
            message.id,
            [chunk.id],
        )

    assert len(citations) == 1
    assert citations[0].chunk_id == chunk.id
    assert citations[0].quote == "quoted chunk"


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

        citation = persist_citations(db, project.id, message.id, [chunk.id])[0]

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

        with pytest.raises(ValueError, match="same project"):
            persist_citations(db, project.id, message.id, [other_chunk.id])

    assert project.id != other_project.id
