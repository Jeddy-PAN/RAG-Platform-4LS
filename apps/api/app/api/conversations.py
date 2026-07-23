import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import AllConversationRead, ConversationDetailRead, ConversationRead
from app.services.conversations import (
    delete_conversation,
    get_conversation,
    list_all_conversations,
    list_conversation_messages,
    list_conversations,
)


router = APIRouter(prefix="/api/projects/{project_id}/conversations", tags=["chat"])
all_router = APIRouter(prefix="/api/conversations", tags=["chat"])


@router.get("", response_model=list[ConversationRead])
def list_project_conversations(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List conversations in one project."""

    return list_conversations(db, project_id)


@router.get("/{conversation_id}", response_model=ConversationDetailRead)
def get_project_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Fetch one conversation with messages."""

    conversation = get_conversation(db, project_id, conversation_id)
    messages = list_conversation_messages(db, project_id, conversation_id)
    return ConversationDetailRead.model_validate(
        {
            "id": conversation.id,
            "project_id": conversation.project_id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": messages,
        }
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Delete one project-scoped conversation."""

    delete_conversation(db, project_id, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@all_router.get("", response_model=list[AllConversationRead])
def list_all_project_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List recent conversations across all projects."""

    return list_all_conversations(db, limit=limit)
