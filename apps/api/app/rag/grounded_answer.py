"""Strict provider contract and local rendering for grounded answers."""

from dataclasses import dataclass, field
import json
import re
from types import MappingProxyType
from typing import Literal, Mapping
import uuid

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.rag.prompting import PromptFacetPolicy, PromptSource


class ProviderCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_number: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=500)


class ProviderClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    claim_index: int = Field(ge=1)
    facet_index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4000)
    conflict_group_index: int | None = Field(default=None, ge=0)
    citations: list[ProviderCitation] = Field(min_length=1, max_length=8)

    @field_validator("text")
    @classmethod
    def text_must_contain_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text must not be whitespace")
        return value


class ProviderGroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["grounded-answer-v1"]
    claims: list[ProviderClaim] = Field(min_length=1, max_length=32)


class GroundedAnswerValidationError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ValidatedAnswerCitation:
    source_number: int
    chunk_id: uuid.UUID
    quote: str


@dataclass(frozen=True)
class ValidatedAnswerClaim:
    claim_index: int
    facet_index: int
    conflict_group_index: int | None
    text: str
    citations: tuple[ValidatedAnswerCitation, ...]


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    model: str
    claims: tuple[ValidatedAnswerClaim, ...] = ()
    allowed_sources: Mapping[int, PromptSource] = field(
        default_factory=lambda: MappingProxyType({})
    )
    citation_sources: list[PromptSource] = field(default_factory=list)
    grounding_status: str = "validated"
    grounding_reason: str | None = None


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GroundedAnswerValidationError("invalid_json")
        result[key] = value
    return result


def parse_provider_answer(content: str) -> ProviderGroundedAnswer:
    if not isinstance(content, str) or not content.strip():
        raise GroundedAnswerValidationError("invalid_json")
    try:
        if len(content.encode("utf-8")) > 65536:
            raise GroundedAnswerValidationError("invalid_json")
        payload = json.loads(
            content,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError, UnicodeError):
        raise GroundedAnswerValidationError("invalid_json") from None
    if not isinstance(payload, dict):
        raise GroundedAnswerValidationError("invalid_schema")
    try:
        return ProviderGroundedAnswer.model_validate(payload)
    except ValidationError:
        raise GroundedAnswerValidationError("invalid_schema") from None


def _substring_occurrence_count(text: str, quote: str) -> int:
    """Count overlapping exact substring occurrences for stable quote ranges."""

    count = 0
    start = 0
    while True:
        index = text.find(quote, start)
        if index < 0:
            return count
        count += 1
        start = index + 1


def validate_provider_answer(
    content: str,
    citation_map: Mapping[int, PromptSource],
    facet_policies: tuple[PromptFacetPolicy, ...],
) -> tuple[ValidatedAnswerClaim, ...]:
    parsed = parse_provider_answer(content)
    policies = {policy.facet_index: policy for policy in facet_policies}
    if len(policies) != len(facet_policies):
        raise GroundedAnswerValidationError("unknown_facet")
    claims = parsed.claims
    if [claim.claim_index for claim in claims] != list(range(1, len(claims) + 1)):
        raise GroundedAnswerValidationError("invalid_schema")
    covered_seen: set[int] = set()
    conflict_seen: dict[tuple[int, int], bool] = {}
    bindings: set[tuple[int, int, str]] = set()
    validated: list[ValidatedAnswerClaim] = []
    for claim in claims:
        policy = policies.get(claim.facet_index)
        if policy is None:
            raise GroundedAnswerValidationError("unknown_facet")
        if policy.status == "unresolved":
            raise GroundedAnswerValidationError("source_not_allowed")
        if policy.status == "covered":
            if claim.conflict_group_index is not None:
                raise GroundedAnswerValidationError("invalid_conflict")
            allowed = set(policy.allowed_source_numbers)
        else:
            if claim.conflict_group_index is None or claim.conflict_group_index >= len(policy.conflict_source_groups):
                raise GroundedAnswerValidationError("invalid_conflict")
            allowed = set(policy.conflict_source_groups[claim.conflict_group_index])
            conflict_seen[(claim.facet_index, claim.conflict_group_index)] = True
        citations: list[ValidatedAnswerCitation] = []
        for citation in claim.citations:
            source = citation_map.get(citation.source_number)
            if source is None or citation.source_number not in allowed:
                raise GroundedAnswerValidationError("source_not_allowed")
            quote = citation.quote.strip()
            if not quote or _substring_occurrence_count(source.text, quote) != 1:
                raise GroundedAnswerValidationError("invalid_quote")
            binding = (claim.claim_index, citation.source_number, quote)
            if binding in bindings:
                raise GroundedAnswerValidationError("invalid_quote")
            bindings.add(binding)
            citations.append(ValidatedAnswerCitation(citation.source_number, source.chunk_id, quote))
        if re.search(r"\[\s*source\s+\d+\s*\]", claim.text, re.IGNORECASE):
            raise GroundedAnswerValidationError("invalid_schema")
        covered_seen.add(claim.facet_index)
        validated.append(ValidatedAnswerClaim(claim.claim_index, claim.facet_index, claim.conflict_group_index, claim.text, tuple(citations)))
    for policy in facet_policies:
        if policy.status == "covered" and policy.facet_index not in covered_seen:
            raise GroundedAnswerValidationError("incomplete_coverage")
        if policy.status == "conflicting":
            for group_index in range(len(policy.conflict_source_groups)):
                if not conflict_seen.get((policy.facet_index, group_index)):
                    raise GroundedAnswerValidationError("incomplete_coverage")
    return tuple(validated)


def render_validated_answer(
    claims: tuple[ValidatedAnswerClaim, ...],
    facet_policies: tuple[PromptFacetPolicy, ...],
    question: str,
) -> str:
    chinese = bool(re.search(r"[\u3400-\u9fff]", question))
    notices: list[str] = []
    for policy in facet_policies:
        if policy.status == "unresolved":
            notices.append(f"未找到：{policy.request_text}" if chinese else f"Not found: {policy.request_text}")
        if policy.is_partial:
            notices.append("以上仅覆盖部分上下文。" if chinese else "The answer is based on partial context.")
        if policy.status == "conflicting":
            notices.append("存在相互冲突的来源：" if chinese else "The sources contain conflicting information:")
    ordered_claims = [claim.text for claim in sorted(claims, key=lambda claim: claim.claim_index)]
    if not notices and not ordered_claims:
        raise GroundedAnswerValidationError("incomplete_coverage")
    return "\n".join([*notices, *ordered_claims])


def immutable_sources(citation_map: Mapping[int, PromptSource]) -> Mapping[int, PromptSource]:
    return MappingProxyType(dict(citation_map))
