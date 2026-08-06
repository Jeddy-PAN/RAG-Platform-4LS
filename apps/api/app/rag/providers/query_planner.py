"""Injectable structured query-facet planner provider for Round 4B.

Uses the existing chat-completions transport with a versioned JSON-only prompt
and strict parsing. Request/response bodies are never logged.
"""

import json
import re

from app.core.config import Settings, get_settings
from app.rag.providers.chat import ChatProviderError, OpenAIChatProvider
from app.rag.providers.types import ChatProvider, QueryFacetPlannerProvider
from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    QueryEntity,
    MAX_EVIDENCE_FACETS,
)

_MAX_PLANNER_RESPONSE_LENGTH = 4000

_PLANNER_SYSTEM_PROMPT = (
    "You decompose one user question into at most 4 independent fact "
    "subquestions. Return ONLY a JSON object, no commentary. "
    'Format: {"facets": [{"index": 0, "query": "<grounded subquestion>", '
    '"entity": "<span verbatim from the question>", '
    '"attribute": "<span verbatim from the question>"}]}. '
    "Every entity and attribute span must appear verbatim in the original "
    "question. If the question is a single fact or cannot be split safely, "
    'return {"facets": [{"index": 0, "query": "<the original question>", '
    '"entity": "", "attribute": ""}]}.'
)


class PlannerProviderError(RuntimeError):
    """Raised when structured planning cannot produce a valid plan."""

    def __init__(self, message: str, reason_code: str = "planner_error") -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _normalize_entity(text: str) -> str:
    return re.sub(r"[^a-z0-9㐀-鿿]+", "", text.casefold())


def _parse_plan_response(
    content: str | None,
    question: str,
    max_facets: int,
) -> EvidenceQueryPlan:
    """Strictly parse and validate a structured planner response."""
    if not content or len(content) > _MAX_PLANNER_RESPONSE_LENGTH:
        raise PlannerProviderError("planner response empty or too long")
    try:
        data = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise PlannerProviderError("planner returned invalid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("facets"), list):
        raise PlannerProviderError("planner response missing facets")

    raw_facets: list[tuple[int, str, str, str]] = []
    for item in data["facets"]:
        if not isinstance(item, dict):
            raise PlannerProviderError("invalid facet entry")
        if set(item) != {"index", "query", "entity", "attribute"}:
            raise PlannerProviderError("invalid facet schema")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise PlannerProviderError("invalid facet index")
        query = item.get("query")
        entity = item.get("entity")
        attribute = item.get("attribute")
        if not isinstance(entity, str) or not isinstance(attribute, str):
            raise PlannerProviderError("invalid facet spans")
        if not isinstance(query, str) or not query.strip():
            raise PlannerProviderError("invalid facet query")
        for span in (entity, attribute):
            if span and (not isinstance(span, str) or span not in question):
                raise PlannerProviderError("ungrounded facet span")
        raw_facets.append((index, query.strip(), entity, attribute))

    if not raw_facets:
        raise PlannerProviderError("planner returned no facets")
    if len(raw_facets) > max_facets or len(raw_facets) > MAX_EVIDENCE_FACETS:
        raise PlannerProviderError("too many facets")
    if [index for index, _, _, _ in raw_facets] != list(range(len(raw_facets))):
        raise PlannerProviderError("facet indexes must be contiguous")

    facets = []
    for index, query, entity, attribute in raw_facets:
        entities = (
            (QueryEntity(text=entity, normalized=_normalize_entity(entity)),)
            if entity
            else ()
        )
        attributes = (attribute,) if attribute else ()
        facets.append(
            EvidenceFacet(
                index=index,
                query=query,
                entities=entities,
                attributes=attributes,
            )
        )
    return EvidenceQueryPlan(
        original_query=question,
        facets=tuple(facets),
        route="structured",
        confidence=0.7,
    )


class OpenAIFacetPlannerProvider(QueryFacetPlannerProvider):
    """Structured planner using the existing chat-completions transport."""

    def __init__(self, chat_provider: ChatProvider | None = None) -> None:
        self._chat_provider = chat_provider

    def plan(self, question: str, max_facets: int = 4) -> EvidenceQueryPlan:
        if self._chat_provider is None:
            settings = get_settings()
            _validate_planner_settings(settings)
            provider = OpenAIChatProvider.from_settings()
        else:
            provider = self._chat_provider
        try:
            result = provider.generate_chat_completion(
                [
                    {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
            )
        except ChatProviderError as exc:
            raise PlannerProviderError(
                "planner provider failed",
                reason_code="planner_provider_error",
            ) from exc
        return _parse_plan_response(result.content, question, max_facets)


def _validate_planner_settings(settings: Settings) -> None:
    if (
        settings.llm_provider.strip().lower() not in {"openai", "openai_compatible"}
        or not settings.llm_base_url.strip()
        or not settings.llm_api_key.strip()
        or not settings.llm_model.strip()
    ):
        raise PlannerProviderError(
            "planner provider configuration is unavailable",
            reason_code="planner_configuration",
        )
