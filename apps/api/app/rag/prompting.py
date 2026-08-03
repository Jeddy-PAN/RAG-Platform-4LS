from dataclasses import dataclass

from app.rag.retrieval.types import (
    FacetTableContextCoverage,
    RetrievalCandidate,
    TableContextCoverage,
    TableSelectionPlan,
)


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
    context_partial: bool = False,
    table_context: TableContextCoverage | None = None,
    table_selection_plan: TableSelectionPlan | None = None,
    table_contexts: list[FacetTableContextCoverage] | None = None,
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
    )

    if table_selection_plan is not None:
        facet_source_map: dict[int, list[int]] = {
            outcome.facet.index: [] for outcome in table_selection_plan.outcomes
        }
        for source_number, chunk in enumerate(retrieved_chunks, start=1):
            for facet_index in (chunk.score_metadata or {}).get(
                "table_facet_indexes", []
            ):
                if facet_index in facet_source_map:
                    facet_source_map[facet_index].append(source_number)

        facet_lines: list[str] = []
        for outcome in table_selection_plan.outcomes:
            facet = outcome.facet
            sources = ", ".join(
                f"[Source {source_number}]"
                for source_number in facet_source_map.get(facet.index, [])
            )
            facet_lines.append(
                f"Facet {facet.index + 1}: {facet.query}; sources: {sources}"
            )

        partial_lines: list[str] = []
        if table_contexts:
            for context in table_contexts:
                if not context.is_partial:
                    continue
                ranges = ", ".join(
                    str(start) if start == end else f"{start}-{end}"
                    for start, end in context.coverage.row_ranges
                )
                if ranges and context.coverage.total_rows:
                    row_text = f"provided rows {ranges} of {context.coverage.total_rows}."
                elif ranges:
                    row_text = f"provided rows {ranges}."
                else:
                    row_text = "no rows were retained."
                for facet_index in context.facet_indexes:
                    partial_lines.append(
                        f"Facet {facet_index + 1} is partial; {row_text}"
                    )
        if partial_lines:
            partial_lines.append(
                "Do not state or imply that the compound answer is complete."
            )

        compound_section = "\n".join(
            [
                "Answer every resolved facet separately and cite its mapped "
                "source numbers. Keep facts attached to the facet and source "
                "group that supports them.",
                *facet_lines,
                *partial_lines,
            ]
        )
        system_content = (
            system_content + compound_section + "\n\n" + "\n\n".join(source_blocks)
        )
    else:
        partial_instruction = ""
        if context_partial:
            coverage = ""
            if table_context:
                ranges = ", ".join(
                    str(start) if start == end else f"{start}-{end}"
                    for start, end in table_context.row_ranges
                )
                if ranges and table_context.total_rows:
                    coverage = (
                        f" The provided context covers data rows {ranges} of "
                        f"{table_context.total_rows}."
                    )
                elif ranges:
                    coverage = f" The provided context covers data rows {ranges}."
            partial_instruction = (
                "IMPORTANT: The selected table context is partial because it exceeded "
                "the context budget. Do not state or imply that the answer lists all "
                "rows or is complete. Explicitly tell the user that only part of the "
                f"table is covered.{coverage}\n\n"
            )
        system_content = (
            system_content + partial_instruction + "\n\n".join(source_blocks)
        )
    messages = [{"role": "system", "content": system_content}]
    messages.extend(recent_messages)
    messages.append({"role": "user", "content": question})
    return ChatPrompt(messages=messages, citation_map=citation_map, should_refuse=False)
