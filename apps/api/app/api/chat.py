import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.chat_service import send_chat_message
from app.schemas.chat import ChatCitationRead, ChatMessageRequest, ChatMessageResponse


router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


@router.post("/messages", response_model=ChatMessageResponse)
def send_message(
    project_id: uuid.UUID,
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """Send one project-scoped chat message and return a grounded answer."""

    result = send_chat_message(
        db,
        project_id=project_id,
        conversation_id=payload.conversation_id,
        message=payload.message,
        retrieval_mode=payload.retrieval.mode,
        top_k=payload.retrieval.top_k,
        vector_weight=payload.retrieval.vector_weight,
        keyword_weight=payload.retrieval.keyword_weight,
    )
    return ChatMessageResponse(
        conversation_id=result["conversation"].id,
        user_message_id=result["user_message"].id,
        assistant_message_id=result["assistant_message"].id,
        answer=result["answer"],
        retrieval_log_id=result["retrieval_log_id"],
        model=result["model"],
        latency_ms=result["latency_ms"],
        citations=[
            ChatCitationRead(
                citation_index=citation.citation_index,
                chunk_id=citation.chunk_id,
                quote=citation.quote,
                citation_metadata=citation.citation_metadata,
            )
            for citation in result["citations"]
        ],
    )
