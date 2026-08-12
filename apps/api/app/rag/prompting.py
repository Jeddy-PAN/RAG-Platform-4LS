from dataclasses import dataclass

from app.rag.retrieval.evidence_types import EvidenceSelectionPlan
from app.rag.source_metadata import public_source_metadata
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
    evidence_selection_plan: EvidenceSelectionPlan | None = None,
) -> ChatPrompt:
    """Build grounded chat messages from retrieved chunks and recent history."""

    if not retrieved_chunks:
        return ChatPrompt(messages=[], citation_map={}, should_refuse=True)

    citation_map: dict[int, PromptSource] = {}
    source_blocks: list[str] = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        safe_metadata = public_source_metadata(chunk.source_metadata)
        citation_map[index] = PromptSource(
            citation_index=index,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            source_metadata=safe_metadata,
            text=chunk.text,
        )
        source_blocks.append(
            "\n".join(
                [
                    f"[Source {index}]",
                    f"chunk_id: {chunk.chunk_id}",
                    f"document: {chunk.document_name}",
                    f"metadata: {safe_metadata}",
                    f"content: {chunk.text}",
                ]
            )
        )

    if (
        evidence_selection_plan is not None
        and evidence_selection_plan.coverage
        and all(
            coverage.status == "unresolved"
            for coverage in evidence_selection_plan.coverage
        )
    ):
        return ChatPrompt(messages=[], citation_map={}, should_refuse=True)

    system_content = (
        "You are a project-scoped RAG assistant. Answer only from the provided "
        "knowledge base context. If the context is insufficient, say you cannot "
        "answer from the selected knowledge base. Cite sources by referring to "
        "the provided source numbers.\n\n"
    )

    if evidence_selection_plan is not None:
        source_by_chunk = {
            chunk.chunk_id: index
            for index, chunk in enumerate(retrieved_chunks, start=1)
        }
        chunk_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}

        def source_allowed(chunk_id: object, facet_index: int) -> bool:
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                return False
            mapped_facets = (chunk.score_metadata or {}).get("evidence_facet_indexes")
            return mapped_facets is None or facet_index in mapped_facets

        facet_by_index = {
            facet.index: facet for facet in evidence_selection_plan.query_plan.facets
        }
        coverage_by_index = {
            coverage.facet_index: coverage
            for coverage in evidence_selection_plan.coverage
        }
        expected_indexes = set(facet_by_index)
        if set(coverage_by_index) != expected_indexes:
            return ChatPrompt(messages=[], citation_map={}, should_refuse=True)

        for coverage in evidence_selection_plan.coverage:
            selected_ids = set(coverage.selected_chunk_ids)
            if coverage.status == "covered":
                if (
                    not selected_ids
                    or not selected_ids <= set(source_by_chunk)
                    or not all(
                        source_allowed(chunk_id, coverage.facet_index)
                        for chunk_id in selected_ids
                    )
                ):
                    return ChatPrompt(messages=[], citation_map={}, should_refuse=True)
            elif coverage.status == "conflicting":
                if len(coverage.conflict_groups) < 2:
                    return ChatPrompt(messages=[], citation_map={}, should_refuse=True)
                group_sets = [set(group) for group in coverage.conflict_groups]
                if any(
                    not group
                    or not set(group) <= selected_ids
                    or not set(group) <= set(source_by_chunk)
                    or not all(
                        source_allowed(chunk_id, coverage.facet_index)
                        for chunk_id in group
                    )
                    for group in coverage.conflict_groups
                ) or any(
                    left & right
                    for index, left in enumerate(group_sets)
                    for right in group_sets[index + 1 :]
                ):
                    return ChatPrompt(messages=[], citation_map={}, should_refuse=True)
            elif not selected_ids <= set(source_by_chunk):
                return ChatPrompt(messages=[], citation_map={}, should_refuse=True)

        facet_lines: list[str] = []
        for coverage in evidence_selection_plan.coverage:
            facet_label = f"Facet {coverage.facet_index + 1}"
            facet = facet_by_index[coverage.facet_index]
            facet_description = f"requested item: {facet.query}"
            if coverage.status == "unresolved":
                unresolved_instruction = (
                    " Do not use or cite any source for this facet."
                    if coverage.reason == "budget_exhausted"
                    else ""
                )
                facet_lines.append(
                    f"{facet_label} (unresolved): {facet_description}; this "
                    "requested item was not found in the selected knowledge base."
                    + unresolved_instruction
                )
            elif coverage.status == "conflicting":
                groups = "; ".join(
                    ", ".join(
                        f"[Source {source_by_chunk[chunk_id]}]"
                        for chunk_id in group
                        if chunk_id in source_by_chunk
                    )
                    for group in coverage.conflict_groups
                )
                facet_lines.append(
                    f"{facet_label} (conflicting): {facet_description}; sources "
                    f"disagree: {groups}"
                )
            else:
                sources = ", ".join(
                    f"[Source {source_by_chunk[chunk_id]}]"
                    for chunk_id in coverage.selected_chunk_ids
                    if chunk_id in source_by_chunk
                )
                facet_lines.append(
                    f"{facet_label} (covered): {sources}; {facet_description}"
                )

        policy_lines = [
            "Answer every covered facet separately and only from its mapped "
            "source numbers.",
            "For every unresolved facet, explicitly state that the requested "
            "item was not found in the selected knowledge base. Do not state or "
            "imply that the compound answer is complete.",
        ]
        if any(
            coverage.status == "conflicting"
            for coverage in evidence_selection_plan.coverage
        ):
            policy_lines.append(
                "For conflicting facets, present each source group's value "
                "separately and cite its sources. Never merge values or pick a "
                "winner."
            )

        evidence_section = "\n".join(facet_lines + [""] + policy_lines)
        system_content = (
            system_content + evidence_section + "\n\n" + "\n\n".join(source_blocks)
        )
    elif table_selection_plan is not None:
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
