import re
import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import MessageRole
from app.models.retrieval import RetrievalMode
from app.rag.answering import AnswerResult, generate_answer
from app.rag.citations import persist_citations
from app.rag.providers.chat import ChatProviderError
from app.rag.retrieval.service import run_retrieval
from app.rag.retrieval.types import TableSelectionOutcome
from app.services.conversations import (
    get_or_create_conversation,
    get_pending_table_clarification,
    list_recent_messages,
)
from app.services.metrics import record_chat_metric
from app.services.messages import create_message


def _table_selection_metadata(outcome: TableSelectionOutcome | None) -> dict | None:
    """Serialize table identities without exposing internal ranking scores."""

    if outcome is None:
        return None
    return {
        "status": outcome.status,
        "selected": outcome.selected.identity_metadata() if outcome.selected else None,
        "candidates": [candidate.identity_metadata() for candidate in outcome.candidates],
    }


def _build_table_clarification(outcome: TableSelectionOutcome, query: str) -> str:
    """Build a short localized clarification from ambiguous table identities."""

    labels: list[str] = []
    for candidate in outcome.candidates:
        parts = [candidate.document_name]
        if (
            candidate.caption
            and candidate.caption.casefold() not in candidate.document_name.casefold()
        ):
            parts.append(candidate.caption)
        parts.append(f"table {candidate.table_index + 1}")
        labels.append(" - ".join(parts))

    if re.search(r"[\u3400-\u9fff]", query):
        heading = "我找到了多个可能相关的表格。请指定要查询哪一个："
    else:
        heading = "I found multiple relevant tables. Please choose one:"
    choices = "\n".join(f"{index}. {label}" for index, label in enumerate(labels, start=1))
    return f"{heading}\n{choices}"


def _resolve_table_confirmation(
    message: str,
    clarification: dict | None,
) -> tuple[uuid.UUID, int] | None:
    """Resolve an ordinal, filename, or caption reply against pending candidates."""

    if not clarification:
        return None
    candidates = clarification.get("candidates") or []
    lowered = message.strip().casefold()
    ordinal_patterns = (
        (r"^(?:1|first|the first one|option 1|table 1|第一个|第一项|第1个)$", 0),
        (r"^(?:2|second|the second one|option 2|table 2|第二个|第二项|第2个)$", 1),
        (r"^(?:3|third|the third one|option 3|table 3|第三个|第三项|第3个)$", 2),
        (r"^(?:4|fourth|the fourth one|option 4|table 4|第四个|第四项|第4个)$", 3),
    )
    selected_index = next(
        (index for pattern, index in ordinal_patterns if re.fullmatch(pattern, lowered)),
        None,
    )

    if selected_index is None:
        normalized_message = re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", lowered).strip()
        message_tokens = {token for token in normalized_message.split() if len(token) > 1}
        for index, candidate in enumerate(candidates):
            labels = [candidate.get("document_name") or "", candidate.get("caption") or ""]
            for label in labels:
                label = label.rsplit(".", 1)[0]
                normalized_label = re.sub(
                    r"[^a-z0-9\u3400-\u9fff]+", " ", label.casefold()
                ).strip()
                label_tokens = {token for token in normalized_label.split() if len(token) > 1}
                if normalized_label and (
                    normalized_label in normalized_message
                    or normalized_message in normalized_label
                    or len(message_tokens & label_tokens) >= 2
                ):
                    selected_index = index
                    break
            if selected_index is not None:
                break

    if selected_index is None or selected_index >= len(candidates):
        return None
    selected = candidates[selected_index]
    try:
        return uuid.UUID(selected["document_id"]), int(selected["table_index"])
    except (KeyError, TypeError, ValueError):
        return None


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
    pending_clarification = get_pending_table_clarification(db, project_id, conversation.id)
    preferred_table = _resolve_table_confirmation(message, pending_clarification)
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
        preferred_document_id=preferred_table[0] if preferred_table else None,
        preferred_table_index=preferred_table[1] if preferred_table else None,
    )
    generation_started = time.perf_counter()
    try:
        if retrieval.table_selection and retrieval.table_selection.status == "ambiguous":
            answer = AnswerResult(
                answer=_build_table_clarification(retrieval.table_selection, message),
                model="local-table-clarification",
            )
        else:
            answer = generate_answer(
                question=message,
                retrieved_chunks=retrieval.results,
                recent_messages=recent_messages,
                context_partial=retrieval.context_partial,
                table_context=retrieval.table_context,
            )
    except ChatProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    generation_latency_ms = int((time.perf_counter() - generation_started) * 1000)

    message_metadata = {
        "model": answer.model,
        "retrieval_log_id": str(retrieval.retrieval_log_id),
        "context_partial": retrieval.context_partial,
    }
    selection_metadata = _table_selection_metadata(retrieval.table_selection)
    if selection_metadata:
        message_metadata["table_selection"] = selection_metadata
    if retrieval.table_context:
        message_metadata["table_context"] = retrieval.table_context.to_metadata()

    assistant_message = create_message(
        db,
        project_id,
        conversation.id,
        MessageRole.assistant,
        answer.answer,
        metadata=message_metadata,
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
    record_chat_metric(
        db,
        project_id=project_id,
        conversation_id=conversation.id,
        retrieval_log_id=retrieval.retrieval_log_id,
        model=answer.model,
        latency_ms=latency_ms,
        retrieval_latency_ms=retrieval.latency_ms,
        generation_latency_ms=generation_latency_ms,
        citation_count=len(citations),
    )
    db.commit()
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
