import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import MessageRole
from app.models.retrieval import RetrievalMode
from app.rag.answering import generate_answer
from app.rag.citations import persist_citations
from app.rag.providers.chat import ChatProviderError
from app.rag.retrieval.service import run_retrieval
from app.services.conversations import get_or_create_conversation, list_recent_messages
from app.services.messages import create_message


def send_chat_message(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    message: str,
    retrieval_mode: RetrievalMode = RetrievalMode.hybrid,
    top_k: int = 8,
    vector_weight: float = 0.65,
    keyword_weight: float = 0.35,
    reranker_enabled: bool = False,
    reranker_candidate_limit: int = 40,
):
    """Persist a user message, run retrieval, generate an answer, and cite context."""

    started = time.perf_counter()
    conversation = get_or_create_conversation(
        db,
        project_id,
        conversation_id,
        title=message[:80],
    )
    recent_messages = list_recent_messages(db, project_id, conversation.id)
    user_message = create_message(
        db,
        project_id,
        conversation.id,
        MessageRole.user,
        message,
    )
    db.commit()

    retrieval = run_retrieval(
        db,
        project_id=project_id,
        query=message,
        mode=retrieval_mode,
        top_k=top_k,
        vector_weight=vector_weight,
        keyword_weight=keyword_weight,
        reranker_enabled=reranker_enabled,
        reranker_candidate_limit=reranker_candidate_limit,
    )
    try:
        answer = generate_answer(
            question=message,
            retrieved_chunks=retrieval.results,
            recent_messages=recent_messages,
        )
    except ChatProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    assistant_message = create_message(
        db,
        project_id,
        conversation.id,
        MessageRole.assistant,
        answer.answer,
        metadata={"model": answer.model, "retrieval_log_id": str(retrieval.retrieval_log_id)},
    )
    citations = persist_citations(
        db,
        project_id,
        assistant_message.id,
        [source.chunk_id for source in answer.citation_sources],
    )
    db.commit()
    for citation in citations:
        db.refresh(citation)
    db.refresh(user_message)
    db.refresh(assistant_message)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "conversation": conversation,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "answer": answer.answer,
        "citations": citations,
        "retrieval_log_id": retrieval.retrieval_log_id,
        "model": answer.model,
        "latency_ms": latency_ms,
    }
