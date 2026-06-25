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
