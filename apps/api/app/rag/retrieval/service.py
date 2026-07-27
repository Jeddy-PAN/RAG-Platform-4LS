import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.retrieval import RetrievalMode
from app.rag.providers.embeddings import (
    EmbeddingProviderError,
    get_embedding_provider_from_settings,
)
from app.rag.providers.types import EmbeddingProvider
from app.rag.retrieval.hybrid import fuse_retrieval_results
from app.rag.retrieval.keyword import retrieve_keyword
from app.rag.retrieval.rerankers import KeywordOverlapReranker, rerank_candidates
from app.rag.retrieval.types import RetrievalResult
from app.rag.retrieval.vector import retrieve_vector
from app.services.retrieval_logs import create_retrieval_log


def run_retrieval(
    db: Session,
    project_id: uuid.UUID,
    query: str,
    mode: RetrievalMode,
    top_k: int,
    vector_weight: float = 0.65,
    keyword_weight: float = 0.35,
    similarity_threshold: float = 0.0,
    embedding_provider: EmbeddingProvider | None = None,
    reranker_enabled: bool = False,
    reranker_candidate_limit: int = 40,
    document_id: uuid.UUID | None = None,
) -> RetrievalResult:
    """Run project-scoped retrieval and persist debug logs.

    When *document_id* is provided, retrieval is scoped to that document.
    When a table-intent query is detected and table chunks are found in
    the initial results, same-table expansion loads the full table or
    row groups, and parent/child deduplication removes overlapping rows.
    """

    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    from app.rag.retrieval.table_expansion import (
        apply_context_budget,
        dedup_parent_child,
        detect_table_intent,
        expand_same_table,
        select_target_table,
    )

    started = time.perf_counter()
    table_intent = False
    is_full_table = False
    expansion_applied = False
    selection_result: dict | None = None
    context_partial = False
    initial_limit = max(top_k, reranker_candidate_limit) if reranker_enabled else top_k

    try:
        # ── Intent detection (before retrieval) ──
        table_intent, is_full_table = detect_table_intent(query)

        # Wide candidate pool for full-table queries so the target table
        # does not need to enter the final top_k before selection.
        if is_full_table:
            wide_limit = max(top_k * 5, 40)
        else:
            wide_limit = initial_limit

        if mode == RetrievalMode.keyword:
            results = retrieve_keyword(db, project_id, query, wide_limit, document_id=document_id)
        elif mode == RetrievalMode.vector:
            provider = embedding_provider or get_embedding_provider_from_settings()
            query_embedding = provider.embed_texts([query])[0]
            results = retrieve_vector(
                db, project_id, query_embedding, wide_limit,
                similarity_threshold=similarity_threshold,
                document_id=document_id,
            )
        else:
            provider = embedding_provider or get_embedding_provider_from_settings()
            query_embedding = provider.embed_texts([query])[0]
            # Hybrid: use wider pool for table-intent, but don't fuse-truncate yet
            hybrid_limit = max(wide_limit * 3, 60) if is_full_table else max(top_k * 3, 20, wide_limit)
            vector_results = retrieve_vector(
                db, project_id, query_embedding, hybrid_limit,
                similarity_threshold=similarity_threshold,
                document_id=document_id,
            )
            keyword_results = retrieve_keyword(
                db, project_id, query, hybrid_limit, document_id=document_id,
            )
            # Fuse without truncating to top_k — table selection needs the full pool
            results = fuse_retrieval_results(
                vector_results, keyword_results,
                top_k=max(top_k, hybrid_limit),  # keep all for now
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
            )

        # ── Table-aware selection and expansion ──
        if is_full_table:
            sel = select_target_table(query, results)
            selection_result = {
                "status": sel.status,
                "score": sel.score,
                "score_breakdown": sel.score_breakdown,
                "reason": sel.reason,
            }

            if sel.status == "selected":
                if sel.document_id is not None and sel.table_index is not None:
                    expanded = expand_same_table(db, project_id, sel.document_id, sel.table_index)
                    if expanded:
                        non_table = [
                            c for c in results
                            if (c.source_metadata or {}).get("table_chunk_type") not in
                               ("table", "table_group", "table_row", "table_header")
                            and c.document_id == sel.document_id
                        ]
                        results = expanded + non_table
                        results = dedup_parent_child(results)
                        results, context_partial = apply_context_budget(results)
                        expansion_applied = True
                        selection_result["document_name"] = sel.document_name
                        selection_result["table_index"] = sel.table_index
                        selection_result["alternatives"] = sel.alternatives
                    else:
                        # Expansion returned empty — fall back
                        results = results[:top_k]
                        selection_result["fallback_to_normal"] = True
                else:
                    results = results[:top_k]
                    selection_result["fallback_to_normal"] = True

            elif sel.status == "ambiguous":
                results = results[:top_k]
                selection_result["alternatives"] = sel.alternatives

            else:  # "none" or "insufficient_score" — fall back to normal retrieval
                results = results[:top_k]
                selection_result["fallback_to_normal"] = True

        # ── Final truncation ──
        if reranker_enabled:
            actual_top_k = top_k if not expansion_applied else max(top_k, len(results))
            results = rerank_candidates(query, results, top_k=actual_top_k, provider=KeywordOverlapReranker())
        elif not expansion_applied:
            results = results[:top_k]
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    log_metadata = {
        "vector_weight": vector_weight,
        "keyword_weight": keyword_weight,
        "similarity_threshold": similarity_threshold,
        "reranker_enabled": reranker_enabled,
        "reranker": "keyword_overlap" if reranker_enabled else None,
        "reranker_candidate_limit": initial_limit if reranker_enabled else None,
        "table_intent": table_intent,
        "is_full_table": is_full_table,
        "expansion_applied": expansion_applied,
        "context_partial": context_partial,
        "table_selection": selection_result,
    }
    log = create_retrieval_log(
        db,
        project_id=project_id,
        query=query,
        mode=mode,
        top_k=top_k,
        latency_ms=latency_ms,
        results=results,
        metadata=log_metadata,
    )
    return RetrievalResult(
        query=query,
        mode=mode.value,
        top_k=top_k,
        latency_ms=latency_ms,
        results=results,
        retrieval_log_id=log.id,
    )
