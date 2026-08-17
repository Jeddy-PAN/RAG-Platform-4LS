from app.rag.grounded_answer import (
    AnswerResult,
    GroundedAnswerValidationError,
    immutable_sources,
    render_validated_answer,
    validate_provider_answer,
)
from app.rag.prompting import PromptSource, build_chat_prompt
from app.rag.providers.chat import OpenAIChatProvider
from app.rag.providers.types import ChatProvider
from app.rag.retrieval.evidence_types import EvidenceSelectionPlan
from app.rag.retrieval.types import (
    FacetTableContextCoverage,
    RetrievalCandidate,
    TableContextCoverage,
    TableSelectionPlan,
)


NO_ANSWER_MESSAGE = (
    "I cannot answer this from the selected knowledge base. The retrieved "
    "documents do not contain enough relevant information."
)


def generate_answer(
    question: str,
    retrieved_chunks: list[RetrievalCandidate],
    recent_messages: list[dict[str, str]],
    chat_provider: ChatProvider | None = None,
    context_partial: bool = False,
    table_context: TableContextCoverage | None = None,
    table_selection_plan: TableSelectionPlan | None = None,
    table_contexts: list[FacetTableContextCoverage] | None = None,
    evidence_selection_plan: EvidenceSelectionPlan | None = None,
) -> AnswerResult:
    """Generate a grounded answer or a local no-answer refusal."""

    prompt = build_chat_prompt(
        question,
        retrieved_chunks,
        recent_messages,
        context_partial=context_partial,
        table_context=table_context,
        table_selection_plan=table_selection_plan,
        table_contexts=table_contexts,
        evidence_selection_plan=evidence_selection_plan,
    )
    if prompt.should_refuse:
        return AnswerResult(
            answer=NO_ANSWER_MESSAGE,
            model="local-refusal",
            grounding_status="local_refusal",
        )

    provider = chat_provider or OpenAIChatProvider.from_settings()
    result = provider.generate_chat_completion(prompt.messages, temperature=0.1)
    try:
        claims = validate_provider_answer(
            result.content,
            prompt.citation_map,
            prompt.facet_policies,
        )
        answer = render_validated_answer(claims, prompt.facet_policies, question)
    except GroundedAnswerValidationError as exc:
        return AnswerResult(
            answer=NO_ANSWER_MESSAGE,
            model="local-grounding-refusal",
            grounding_status="contract_refusal",
            grounding_reason=exc.reason,
        )
    used_sources: list[PromptSource] = []
    seen: set[int] = set()
    for claim in claims:
        for citation in claim.citations:
            if citation.source_number not in seen:
                seen.add(citation.source_number)
                used_sources.append(prompt.citation_map[citation.source_number])
    return AnswerResult(
        answer=answer,
        model=result.model,
        claims=claims,
        allowed_sources=immutable_sources(prompt.citation_map),
        citation_sources=used_sources,
    )
