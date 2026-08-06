"""Production provider boundaries for generic Round 4B evidence facets."""

import json
import uuid
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.rag.providers.chat import ChatProviderError, OpenAIChatProvider
from app.rag.providers.query_planner import OpenAIFacetPlannerProvider
from app.rag.providers.types import (
    ChatProvider,
    FacetEvidenceAssessor,
    QueryFacetPlannerProvider,
)
from app.rag.retrieval.evidence_types import (
    EvidenceQueryPlan,
    FacetAssessment,
)

_MAX_ASSESSOR_RESPONSE_LENGTH = 3000
_MAX_ASSESSOR_CANDIDATES = 8
_MAX_CANDIDATE_SNIPPET_LENGTH = 1200

_ASSESSOR_SYSTEM_PROMPT = (
    "You assess bounded evidence for one requested fact. Return ONLY a JSON "
    "object with exactly these keys: facet_index, supporting_chunk_ids, "
    "conflict_groups. Use only the supplied chunk IDs. Never return values, "
    "credentials, explanations, or any other key. Put distinct claims in "
    "separate conflict groups; use an empty conflict_groups list when there "
    "is no validated disagreement."
)


class AssessorProviderError(RuntimeError):
    """Raised when bounded evidence assessment cannot produce strict output."""


@dataclass(frozen=True)
class Round4BProviderBundle:
    """Providers injected at the chat/eval orchestration boundary."""

    planner_provider: QueryFacetPlannerProvider | None
    evidence_assessor: FacetEvidenceAssessor | None


def _validate_chat_settings(settings: Settings, provider_name: str) -> None:
    if (
        settings.llm_provider.strip().lower() not in {"openai", "openai_compatible"}
        or not settings.llm_base_url.strip()
        or not settings.llm_api_key.strip()
        or not settings.llm_model.strip()
    ):
        raise AssessorProviderError(
            f"{provider_name} configuration is unavailable"
        )


def _parse_assessment_response(
    content: str | None,
    *,
    facet_index: int,
    candidate_ids: set[uuid.UUID],
) -> FacetAssessment:
    """Strictly parse IDs and reject values or ungrounded assessor output."""

    if not content or len(content) > _MAX_ASSESSOR_RESPONSE_LENGTH:
        raise AssessorProviderError("assessor response empty or too long")
    try:
        payload = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise AssessorProviderError("assessor returned invalid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "facet_index",
        "supporting_chunk_ids",
        "conflict_groups",
    }:
        raise AssessorProviderError("assessor response schema mismatch")
    if payload["facet_index"] != facet_index or isinstance(
        payload["facet_index"], bool
    ) or not isinstance(payload["facet_index"], int):
        raise AssessorProviderError("assessor facet index mismatch")

    raw_supporting = payload["supporting_chunk_ids"]
    raw_groups = payload["conflict_groups"]
    if not isinstance(raw_supporting, list) or not isinstance(raw_groups, list):
        raise AssessorProviderError("assessor IDs must be lists")

    def parse_id(value: object) -> uuid.UUID:
        if not isinstance(value, str):
            raise AssessorProviderError("assessor chunk ID is invalid")
        try:
            chunk_id = uuid.UUID(value)
        except (ValueError, AttributeError) as exc:
            raise AssessorProviderError("assessor chunk ID is invalid") from exc
        if chunk_id not in candidate_ids:
            raise AssessorProviderError("assessor returned an unknown chunk ID")
        return chunk_id

    supporting = tuple(parse_id(value) for value in raw_supporting)
    if len(supporting) != len(set(supporting)):
        raise AssessorProviderError("assessor returned duplicate supporting IDs")

    groups: list[tuple[uuid.UUID, ...]] = []
    grouped_ids: set[uuid.UUID] = set()
    for raw_group in raw_groups:
        if not isinstance(raw_group, list) or not raw_group:
            raise AssessorProviderError("assessor conflict group is empty")
        group = tuple(parse_id(value) for value in raw_group)
        if len(group) != len(set(group)) or grouped_ids & set(group):
            raise AssessorProviderError("assessor conflict groups overlap")
        if not set(group) <= set(supporting):
            raise AssessorProviderError("assessor group is not supporting evidence")
        grouped_ids.update(group)
        groups.append(group)

    return FacetAssessment(
        facet_index=facet_index,
        supporting_chunk_ids=supporting,
        conflict_groups=tuple(groups),
    )


class OpenAIFacetEvidenceAssessor(FacetEvidenceAssessor):
    """Bounded JSON assessor using the configured chat-completions transport."""

    def __init__(self, chat_provider: ChatProvider | None = None) -> None:
        self._chat_provider = chat_provider

    def assess(
        self,
        plan: EvidenceQueryPlan,
        facet_index: int,
        candidates,
    ) -> FacetAssessment:
        facet = next(
            (item for item in plan.facets if item.index == facet_index),
            None,
        )
        if facet is None:
            raise AssessorProviderError("assessor facet is not in the query plan")

        bounded = list(candidates)[:_MAX_ASSESSOR_CANDIDATES]
        candidate_ids = {candidate.chunk_id for candidate in bounded}
        snippets = [
            {
                "chunk_id": str(candidate.chunk_id),
                "content": (candidate.text or "")[:_MAX_CANDIDATE_SNIPPET_LENGTH],
            }
            for candidate in bounded
        ]
        messages = [
            {"role": "system", "content": _ASSESSOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "facet_index": facet_index,
                        "request": facet.query,
                        "candidates": snippets,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        if self._chat_provider is None:
            settings = get_settings()
            _validate_chat_settings(settings, "assessor")
            provider = OpenAIChatProvider.from_settings()
        else:
            provider = self._chat_provider
        try:
            result = provider.generate_chat_completion(messages, temperature=0.0)
        except ChatProviderError as exc:
            raise AssessorProviderError("assessor provider failed") from exc
        return _parse_assessment_response(
            result.content,
            facet_index=facet_index,
            candidate_ids=candidate_ids,
        )


def get_round4b_providers(settings: Settings | None = None) -> Round4BProviderBundle:
    """Build lazy planner and assessor clients without making network calls."""

    del settings
    return Round4BProviderBundle(
        planner_provider=OpenAIFacetPlannerProvider(),
        evidence_assessor=OpenAIFacetEvidenceAssessor(),
    )
