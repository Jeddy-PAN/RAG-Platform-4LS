import uuid

from sqlalchemy.orm import Session

from app.models.conversation import Message, MessageRole


def create_message(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: MessageRole,
    content: str,
    metadata: dict | None = None,
) -> Message:
    """Create one project-scoped conversation message."""

    message = Message(
        project_id=project_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        message_metadata=metadata or {},
    )
    db.add(message)
    db.flush()
    return message
