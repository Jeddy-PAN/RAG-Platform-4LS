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
) -> RetrievalResult:
    """Run project-scoped retrieval and persist debug logs."""

    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    started = time.perf_counter()
    initial_limit = max(top_k, reranker_candidate_limit) if reranker_enabled else top_k
    try:
        if mode == RetrievalMode.keyword:
            results = retrieve_keyword(db, project_id, query, initial_limit)
        elif mode == RetrievalMode.vector:
            provider = embedding_provider or get_embedding_provider_from_settings()
            query_embedding = provider.embed_texts([query])[0]
            results = retrieve_vector(
                db,
                project_id,
                query_embedding,
                initial_limit,
                similarity_threshold=similarity_threshold,
            )
        else:
            provider = embedding_provider or get_embedding_provider_from_settings()
            query_embedding = provider.embed_texts([query])[0]
            candidate_limit = max(top_k * 3, 20, initial_limit)
            vector_results = retrieve_vector(
                db,
                project_id,
                query_embedding,
                candidate_limit,
                similarity_threshold=similarity_threshold,
            )
            keyword_results = retrieve_keyword(db, project_id, query, candidate_limit)
            results = fuse_retrieval_results(
                vector_results,
                keyword_results,
                top_k=top_k,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
            )
        if reranker_enabled:
            results = rerank_candidates(
                query,
                results,
                top_k=top_k,
                provider=KeywordOverlapReranker(),
            )
        else:
            results = results[:top_k]
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    log = create_retrieval_log(
        db,
        project_id=project_id,
        query=query,
        mode=mode,
        top_k=top_k,
        latency_ms=latency_ms,
        results=results,
        metadata={
            "vector_weight": vector_weight,
            "keyword_weight": keyword_weight,
            "similarity_threshold": similarity_threshold,
            "reranker_enabled": reranker_enabled,
            "reranker": "keyword_overlap" if reranker_enabled else None,
            "reranker_candidate_limit": initial_limit if reranker_enabled else None,
        },
    )
    return RetrievalResult(
        query=query,
        mode=mode.value,
        top_k=top_k,
        latency_ms=latency_ms,
        results=results,
        retrieval_log_id=log.id,
    )
