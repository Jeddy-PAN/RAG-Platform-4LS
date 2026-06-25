import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.project import Project


def ensure_project(db: Session, project_id: uuid.UUID) -> Project:
    """Fetch a project or raise 404."""

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_or_create_conversation(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    title: str | None = None,
) -> Conversation:
    """Create or fetch a project-scoped conversation."""

    ensure_project(db, project_id)
    if conversation_id is None:
        conversation = Conversation(project_id=project_id, title=title)
        db.add(conversation)
        db.flush()
        return conversation

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.project_id == project_id,
        )
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


def list_conversations(db: Session, project_id: uuid.UUID) -> list[Conversation]:
    """List project-scoped conversations."""

    ensure_project(db, project_id)
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.updated_at.desc())
        )
    )


def get_conversation(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation:
    """Fetch one project-scoped conversation."""

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.project_id == project_id,
        )
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


def delete_conversation(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> None:
    """Delete one project-scoped conversation."""

    conversation = get_conversation(db, project_id, conversation_id)
    db.delete(conversation)
    db.commit()


def list_conversation_messages(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> list[Message]:
    """List messages for one project-scoped conversation."""

    get_conversation(db, project_id, conversation_id)
    return list(
        db.scalars(
            select(Message)
            .where(
                Message.project_id == project_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
        )
    )


def list_recent_messages(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Return recent same-project conversation messages for prompt history."""

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.project_id == project_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    )
    messages.reverse()
    return [{"role": message.role.value, "content": message.content} for message in messages]
