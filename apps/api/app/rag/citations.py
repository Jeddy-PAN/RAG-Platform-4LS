"""Persistence of Round6A-validated claim/source quote bindings."""

from dataclasses import dataclass
import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.conversation import MessageCitation
from app.rag.grounded_answer import ValidatedAnswerClaim
from app.rag.prompting import PromptSource
from app.rag.source_metadata import public_source_metadata


class CitationPersistenceError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CitationBinding:
    claim_index: int
    source_number: int
    chunk_id: uuid.UUID
    quote: str
    quote_start: int | None = None
    quote_end: int | None = None


def bindings_from_claims(claims: tuple[ValidatedAnswerClaim, ...]) -> tuple[CitationBinding, ...]:
    return tuple(
        CitationBinding(claim.claim_index, citation.source_number, citation.chunk_id, citation.quote)
        for claim in claims
        for citation in claim.citations
    )


def _quote_range(chunk_text: str, binding: CitationBinding) -> tuple[int, int]:
    quote = binding.quote
    if not quote or not quote.strip() or len(quote) > 500:
        raise CitationPersistenceError("invalid_quote")
    if (binding.quote_start is None) != (binding.quote_end is None):
        raise CitationPersistenceError("invalid_offset")
    if binding.quote_start is not None and binding.quote_end is not None:
        if binding.quote_start < 0 or binding.quote_end < binding.quote_start:
            raise CitationPersistenceError("invalid_offset")
        if chunk_text[binding.quote_start:binding.quote_end] != quote:
            raise CitationPersistenceError("invalid_quote")
        return binding.quote_start, binding.quote_end
    starts: list[int] = []
    start = 0
    while True:
        found = chunk_text.find(quote, start)
        if found < 0:
            break
        starts.append(found)
        start = found + 1
    if len(starts) != 1:
        raise CitationPersistenceError("invalid_quote")
    return starts[0], starts[0] + len(quote)


def persist_citation_bindings(
    db: Session,
    project_id: uuid.UUID,
    assistant_message_id: uuid.UUID,
    bindings: tuple[CitationBinding, ...],
    allowed_sources: Mapping[int, PromptSource],
) -> list[MessageCitation]:
    """Persist only exact claim bindings from the validated Round6A boundary."""

    claim_order: list[int] = []
    for binding in bindings:
        if binding.claim_index not in claim_order:
            claim_order.append(binding.claim_index)
    if claim_order and claim_order != list(range(1, len(claim_order) + 1)):
        raise CitationPersistenceError("invalid_binding")
    rows: list[MessageCitation] = []
    seen: set[tuple[int, int, uuid.UUID, int, int]] = set()
    for binding in bindings:
        if binding.claim_index < 1 or binding.source_number < 1:
            raise CitationPersistenceError("invalid_binding")
        source = allowed_sources.get(binding.source_number)
        if source is None or source.chunk_id != binding.chunk_id:
            raise CitationPersistenceError("source_mismatch")
        chunk = db.scalar(select(Chunk).where(Chunk.id == binding.chunk_id, Chunk.project_id == project_id))
        if chunk is None:
            raise CitationPersistenceError("project_mismatch")
        quote_start, quote_end = _quote_range(chunk.text, binding)
        key = (binding.claim_index, binding.source_number, binding.chunk_id, quote_start, quote_end)
        if key in seen:
            continue
        seen.add(key)
        rows.append(MessageCitation(
            project_id=project_id,
            message_id=assistant_message_id,
            chunk_id=chunk.id,
            citation_index=len(rows) + 1,
            claim_index=binding.claim_index,
            source_number=binding.source_number,
            quote=chunk.text[quote_start:quote_end],
            quote_start=quote_start,
            quote_end=quote_end,
            citation_metadata=public_source_metadata(chunk.source_metadata),
        ))
    db.add_all(rows)
    db.flush()
    return rows
