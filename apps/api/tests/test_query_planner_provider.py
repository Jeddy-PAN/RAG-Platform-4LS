"""Tests for the structured query-facet planner provider and strict parsing."""

import pytest

from app.rag.providers.chat import ChatProviderError, ChatProviderResult
from app.rag.providers.query_planner import (
    PlannerProviderError,
    _parse_plan_response,
)
from app.rag.retrieval.evidence_types import EvidenceQueryPlan


class FakePlannerChat:
    def __init__(self, content: str) -> None:
        self.content = content

    def generate_chat_completion(self, messages, temperature=0.1):
        return ChatProviderResult(content=self.content, model="fake-planner")


def test_parses_valid_multi_facet_plan() -> None:
    content = (
        '{"facets": ['
        '{"index": 0, "query": "find the username for node-17", '
        '"entity": "node-17", "attribute": "username"},'
        '{"index": 1, "query": "find the password for node-17", '
        '"entity": "node-17", "attribute": "password"}]}'
    )
    plan = _parse_plan_response(content, "find the username and password for node-17", 4)
    assert isinstance(plan, EvidenceQueryPlan)
    assert plan.route == "structured"
    assert len(plan.facets) == 2
    assert [facet.index for facet in plan.facets] == [0, 1]


def test_parses_single_facet_fallback() -> None:
    content = (
        '{"facets": [{"index": 0, "query": "what is escalation", '
        '"entity": "", "attribute": ""}]}'
    )
    plan = _parse_plan_response(content, "what is escalation", 4)
    assert len(plan.facets) == 1


def test_malformed_json_rejected() -> None:
    with pytest.raises(PlannerProviderError):
        _parse_plan_response("not json", "q", 4)


def test_missing_facets_rejected() -> None:
    with pytest.raises(PlannerProviderError):
        _parse_plan_response('{"other": 1}', "q", 4)


def test_empty_facets_rejected() -> None:
    with pytest.raises(PlannerProviderError):
        _parse_plan_response('{"facets": []}', "q", 4)


def test_ungrounded_entity_span_rejected() -> None:
    content = (
        '{"facets": [{"index": 0, "query": "q", '
        '"entity": "node-99", "attribute": "username"}]}'
    )
    with pytest.raises(PlannerProviderError):
        _parse_plan_response(content, "find the username for node-17", 4)


def test_ungrounded_attribute_span_rejected() -> None:
    content = (
        '{"facets": [{"index": 0, "query": "q", '
        '"entity": "node-17", "attribute": "secret"}]}'
    )
    with pytest.raises(PlannerProviderError):
        _parse_plan_response(content, "find the username for node-17", 4)


def test_too_many_facets_rejected() -> None:
    content = '{"facets": [' + ",".join(
        f'{{"index": {i}, "query": "q{i}", "entity": "", "attribute": ""}}'
        for i in range(5)
    ) + "]}"
    with pytest.raises(PlannerProviderError):
        _parse_plan_response(content, "q", 4)


def test_non_contiguous_indexes_rejected() -> None:
    content = (
        '{"facets": ['
        '{"index": 0, "query": "q0", "entity": "", "attribute": ""},'
        '{"index": 2, "query": "q1", "entity": "", "attribute": ""}]}'
    )
    with pytest.raises(PlannerProviderError):
        _parse_plan_response(content, "q", 4)


def test_bool_index_rejected() -> None:
    content = (
        '{"facets": [{"index": true, "query": "q0", '
        '"entity": "", "attribute": ""}]}'
    )
    with pytest.raises(PlannerProviderError):
        _parse_plan_response(content, "q", 4)


def test_empty_response_rejected() -> None:
    with pytest.raises(PlannerProviderError):
        _parse_plan_response("", "q", 4)


def test_oversized_response_rejected() -> None:
    with pytest.raises(PlannerProviderError):
        _parse_plan_response("x" * 4001, "q", 4)


def test_provider_error_converts_to_planner_error() -> None:
    from app.rag.providers.query_planner import OpenAIFacetPlannerProvider

    class Broken:
        def generate_chat_completion(self, messages, temperature=0.1):
            raise ChatProviderError("timeout")

    provider = OpenAIFacetPlannerProvider(chat_provider=Broken())
    with pytest.raises(PlannerProviderError):
        provider.plan("find the username and password for node-17")


def test_provider_returns_valid_plan() -> None:
    from app.rag.providers.query_planner import OpenAIFacetPlannerProvider

    content = (
        '{"facets": [{"index": 0, "query": "username node-17", '
        '"entity": "node-17", "attribute": "username"},'
        '{"index": 1, "query": "password node-17", '
        '"entity": "node-17", "attribute": "password"}]}'
    )
    provider = OpenAIFacetPlannerProvider(
        chat_provider=FakePlannerChat(content=content)
    )
    plan = provider.plan("find the username and password for node-17")
    assert len(plan.facets) == 2
