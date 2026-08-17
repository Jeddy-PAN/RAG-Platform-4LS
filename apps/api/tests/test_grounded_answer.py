import json
import uuid

import pytest

from app.rag.grounded_answer import (
    GroundedAnswerValidationError,
    ValidatedAnswerClaim,
    parse_provider_answer,
    render_validated_answer,
    validate_provider_answer,
)
from app.rag.prompting import PromptFacetPolicy, PromptSource


def _source(number: int, text: str) -> PromptSource:
    return PromptSource(number, uuid.uuid4(), uuid.uuid4(), f"doc-{number}", {}, text)


def _payload(*claims, version="grounded-answer-v1"):
    return json.dumps({"version": version, "claims": list(claims)}, ensure_ascii=False)


def _claim(index, text, source=1, quote="Alpha | enabled", facet=0, conflict=None):
    return {
        "claim_index": index,
        "facet_index": facet,
        "text": text,
        "conflict_group_index": conflict,
        "citations": [{"source_number": source, "quote": quote}],
    }


def test_valid_claims_resolve_exact_sources_and_reject_unused_sources_from_compatibility():
    source_map = {1: _source(1, "Alpha | enabled"), 2: _source(2, "Unused evidence")}
    claims = validate_provider_answer(
        _payload(_claim(1, "Alpha is enabled.")),
        source_map,
        (PromptFacetPolicy(0, "alpha", "covered", (1, 2)),),
    )
    assert claims[0].citations[0].chunk_id == source_map[1].chunk_id
    assert claims[0].citations[0].quote == "Alpha | enabled"


@pytest.mark.parametrize("content", ["", "```json\n{}\n```", "prefix {}", "[]"])
def test_parser_rejects_non_raw_json(content):
    with pytest.raises(GroundedAnswerValidationError) as exc:
        parse_provider_answer(content)
    assert exc.value.reason in {"invalid_json", "invalid_schema"}


def test_parser_rejects_duplicate_keys_and_extra_answer():
    with pytest.raises(GroundedAnswerValidationError):
        parse_provider_answer('{"version":"grounded-answer-v1","version":"grounded-answer-v1","claims":[]}')
    with pytest.raises(GroundedAnswerValidationError):
        parse_provider_answer(_payload(_claim(1, "x"))[:-1] + ',"answer":"bypass"}')


def test_parser_rejects_unpaired_unicode_surrogate_as_invalid_json():
    with pytest.raises(GroundedAnswerValidationError) as exc:
        parse_provider_answer("\ud800")
    assert exc.value.reason == "invalid_json"


def test_validation_rejects_unknown_source_facet_and_fabricated_quote():
    policy = (PromptFacetPolicy(0, "alpha", "covered", (1,)),)
    source_map = {1: _source(1, "Alpha | enabled")}
    for claim in (
        _claim(1, "x", source=2, quote="Alpha | enabled"),
        _claim(1, "x", facet=1),
        _claim(1, "x", quote="not present"),
        _claim(1, "x [Source 1]"),
    ):
        with pytest.raises(GroundedAnswerValidationError):
            validate_provider_answer(_payload(claim), source_map, policy)


def test_validation_requires_all_covered_facets_and_conflict_groups():
    source_map = {1: _source(1, "one"), 2: _source(2, "two")}
    policies = (
        PromptFacetPolicy(0, "one", "covered", (1,)),
        PromptFacetPolicy(1, "two", "covered", (2,)),
    )
    with pytest.raises(GroundedAnswerValidationError) as exc:
        validate_provider_answer(_payload(_claim(1, "one", quote="one")), source_map, policies)
    assert exc.value.reason == "incomplete_coverage"
    conflict = (PromptFacetPolicy(0, "conflict", "conflicting", (), ((1,), (2,))),)
    with pytest.raises(GroundedAnswerValidationError):
        validate_provider_answer(_payload(_claim(1, "one", quote="one", conflict=0)), source_map, conflict)


def test_renderer_adds_local_notices_without_provider_wrappers():
    source_map = {1: _source(1, "one")}
    policies = (
        PromptFacetPolicy(0, "one", "covered", (1,), is_partial=True),
        PromptFacetPolicy(1, "two", "unresolved"),
    )
    claims = validate_provider_answer(_payload(_claim(1, "The value is one.", quote="one")), source_map, policies)
    answer = render_validated_answer(claims, policies, "What are one and two?")
    assert "The value is one." in answer
    assert "partial context" in answer
    assert "Not found: two" in answer


def test_renderer_preserves_interleaved_validated_claim_order():
    claims = (
        ValidatedAnswerClaim(1, 1, None, "First fact.", ()),
        ValidatedAnswerClaim(2, 0, None, "Second fact.", ()),
    )
    answer = render_validated_answer(
        claims,
        (PromptFacetPolicy(0, "zero", "covered", (1,)), PromptFacetPolicy(1, "one", "covered", (1,))),
        "question",
    )
    assert answer.splitlines() == ["First fact.", "Second fact."]


def test_validation_rejects_overlapping_quote_matches_and_whitespace_claim_text():
    policy = (PromptFacetPolicy(0, "alpha", "covered", (1,)),)
    with pytest.raises(GroundedAnswerValidationError) as exc:
        validate_provider_answer(_payload(_claim(1, "Fact.", quote="aaa")), {1: _source(1, "aaaa")}, policy)
    assert exc.value.reason == "invalid_quote"
    with pytest.raises(GroundedAnswerValidationError) as exc:
        validate_provider_answer(_payload(_claim(1, "   ")), {1: _source(1, "Alpha | enabled")}, policy)
    assert exc.value.reason == "invalid_schema"
    assert validate_provider_answer(
        _payload(_claim(1, "中文事实。")),
        {1: _source(1, "Alpha | enabled")},
        policy,
    )[0].text == "中文事实。"


def test_validation_allows_cross_claim_quote_reuse_but_rejects_same_claim_duplicate():
    policy = (PromptFacetPolicy(0, "alpha", "covered", (1,)),)
    source_map = {1: _source(1, "Alpha | enabled")}
    claims = validate_provider_answer(
        _payload(_claim(1, "First."), _claim(2, "Second.")), source_map, policy
    )
    assert len(claims) == 2
    duplicated = _claim(1, "First.")
    duplicated["citations"].append({"source_number": 1, "quote": "Alpha | enabled"})
    with pytest.raises(GroundedAnswerValidationError) as exc:
        validate_provider_answer(_payload(duplicated), source_map, policy)
    assert exc.value.reason == "invalid_quote"
