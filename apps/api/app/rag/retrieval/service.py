import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.retrieval import RetrievalMode
from app.rag.providers.embeddings import EmbeddingProviderError, OpenAIEmbeddingProvider
from app.rag.providers.types import EmbeddingProvider
from app.rag.retrieval.hybrid import fuse_retrieval_results
from app.rag.retrieval.keyword import retrieve_keyword
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
) -> RetrievalResult:
    """Run project-scoped retrieval and persist debug logs."""

    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    started = time.perf_counter()
    try:
        if mode == RetrievalMode.keyword:
            results = retrieve_keyword(db, project_id, query, top_k)
        elif mode == RetrievalMode.vector:
            provider = embedding_provider or OpenAIEmbeddingProvider.from_settings()
            query_embedding = provider.embed_texts([query])[0]
            results = retrieve_vector(
                db,
                project_id,
                query_embedding,
                top_k,
                similarity_threshold=similarity_threshold,
            )
        else:
            provider = embedding_provider or OpenAIEmbeddingProvider.from_settings()
            query_embedding = provider.embed_texts([query])[0]
            candidate_limit = max(top_k * 3, 20)
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
