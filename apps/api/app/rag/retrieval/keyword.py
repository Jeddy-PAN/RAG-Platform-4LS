"""Lexical keyword retrieval with cross-candidate n-gram suppression."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.rag.retrieval.lexical import (
    _STRONG_TIERS,
    score_chunk,
    suppress_ngram_for_strong_groups,
    tokenize,
)
from app.rag.retrieval.types import RetrievalCandidate


def retrieve_keyword(
    db: Session,
    project_id: uuid.UUID,
    query: str,
    top_k: int,
    document_id: uuid.UUID | None = None,
) -> list[RetrievalCandidate]:
    query_terms = tokenize(query)
    if not query_terms.ascii_terms and not query_terms.identifier_terms and not query_terms.cjk_terms:
        return []

    conditions = [Chunk.project_id == project_id, Chunk.is_active == True]
    if document_id is not None:
        conditions.append(Chunk.document_id == document_id)

    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(*conditions)
    ).all()

    # Phase 1: score every candidate and collect per-group tier evidence
    evidence: list[tuple[RetrievalCandidate, float, dict, dict[int, str]]] = []
    strong_groups: set[int] = set()

    for chunk, document in rows:
        chunk_terms = tokenize(chunk.text)
        score, meta, group_tiers = score_chunk(query_terms, chunk_terms)
        if score <= 0:
            continue

        candidate = RetrievalCandidate(
            chunk_id=chunk.id, document_id=chunk.document_id,
            document_name=document.filename, chunk_index=chunk.chunk_index,
            text=chunk.text, source_metadata=chunk.source_metadata,
        )
        evidence.append((candidate, score, meta, group_tiers))

        # Track groups that have strong evidence anywhere in the pool
        for gid, tier in group_tiers.items():
            if tier in _STRONG_TIERS:
                strong_groups.add(gid)

    # Phase 2: suppress n-gram for groups that have strong evidence
    adjusted = suppress_ngram_for_strong_groups(evidence, strong_groups)

    # Phase 3: build final candidates with adjusted scores
    candidates: list[RetrievalCandidate] = []
    for candidate, score, meta in adjusted:
        if score <= 0:
            continue
        candidate.keyword_score = float(score)
        candidate.fused_score = float(score)
        candidate.score_metadata = {
            "retrieval_mode": "keyword",
            "exact_identifiers": meta["exact_identifiers"],
            "exact_ascii_terms": meta["exact_ascii_terms"],
            "exact_cjk_terms": meta["exact_cjk_terms"],
            "contained_identifiers": meta["contained_identifiers"],
            "ngram_matches": meta["ngram_matches"],
        }
        candidates.append(candidate)

    candidates.sort(
        key=lambda c: (
            -(c.keyword_score or 0.0),
            c.document_name or "",
            c.chunk_index,
            str(c.document_id),
            str(c.chunk_id),
        ),
    )
    results = candidates[:top_k]
    for index, c in enumerate(results, start=1):
        c.rank = index
    return results
