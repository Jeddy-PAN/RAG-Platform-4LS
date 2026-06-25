from dataclasses import dataclass

from app.rag.retrieval.types import RetrievalCandidate


@dataclass(frozen=True)
class PromptSource:
    """Source entry used for citation persistence."""

    citation_index: int
    chunk_id: object
    document_id: object
    document_name: str
    source_metadata: dict
    text: str


@dataclass(frozen=True)
class ChatPrompt:
    """Assembled chat provider messages and citation map."""

    messages: list[dict[str, str]]
    citation_map: dict[int, PromptSource]
    should_refuse: bool


def build_chat_prompt(
    question: str,
    retrieved_chunks: list[RetrievalCandidate],
    recent_messages: list[dict[str, str]],
) -> ChatPrompt:
    """Build grounded chat messages from retrieved chunks and recent history."""

    if not retrieved_chunks:
        return ChatPrompt(messages=[], citation_map={}, should_refuse=True)

    citation_map: dict[int, PromptSource] = {}
    source_blocks: list[str] = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        citation_map[index] = PromptSource(
            citation_index=index,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            source_metadata=chunk.source_metadata,
            text=chunk.text,
        )
        source_blocks.append(
            "\n".join(
                [
                    f"[Source {index}]",
                    f"chunk_id: {chunk.chunk_id}",
                    f"document: {chunk.document_name}",
                    f"metadata: {chunk.source_metadata}",
                    f"content: {chunk.text}",
                ]
            )
        )

    system_content = (
        "You are a project-scoped RAG assistant. Answer only from the provided "
        "knowledge base context. If the context is insufficient, say you cannot "
        "answer from the selected knowledge base. Cite sources by referring to "
        "the provided source numbers.\n\n"
        + "\n\n".join(source_blocks)
    )
    messages = [{"role": "system", "content": system_content}]
    messages.extend(recent_messages)
    messages.append({"role": "user", "content": question})
    return ChatPrompt(messages=messages, citation_map=citation_map, should_refuse=False)
