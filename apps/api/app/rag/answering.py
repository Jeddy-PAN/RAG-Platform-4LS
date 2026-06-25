from dataclasses import dataclass, field

from app.rag.prompting import PromptSource, build_chat_prompt
from app.rag.providers.chat import OpenAIChatProvider
from app.rag.providers.types import ChatProvider
from app.rag.retrieval.types import RetrievalCandidate


NO_ANSWER_MESSAGE = (
    "I cannot answer this from the selected knowledge base. The retrieved "
    "documents do not contain enough relevant information."
)


@dataclass(frozen=True)
class AnswerResult:
    """Generated answer plus model and citation source data."""

    answer: str
    model: str
    citation_sources: list[PromptSource] = field(default_factory=list)


def generate_answer(
    question: str,
    retrieved_chunks: list[RetrievalCandidate],
    recent_messages: list[dict[str, str]],
    chat_provider: ChatProvider | None = None,
) -> AnswerResult:
    """Generate a grounded answer or a local no-answer refusal."""

    prompt = build_chat_prompt(question, retrieved_chunks, recent_messages)
    if prompt.should_refuse:
        return AnswerResult(answer=NO_ANSWER_MESSAGE, model="local-refusal")

    provider = chat_provider or OpenAIChatProvider.from_settings()
    result = provider.generate_chat_completion(prompt.messages, temperature=0.1)
    return AnswerResult(
        answer=result.content,
        model=result.model,
        citation_sources=list(prompt.citation_map.values()),
    )
