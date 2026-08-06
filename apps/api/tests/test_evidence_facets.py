"""Tests for the conservative generic evidence-facet planner."""

from app.rag.retrieval.evidence_facets import plan_evidence_facets
from app.rag.retrieval.evidence_types import EvidenceFacet, EvidenceQueryPlan, QueryEntity


class RaisingPlanner:
    def plan(self, question: str, max_facets: int = 4):
        raise RuntimeError("provider down")


class SpyPlanner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def plan(self, question: str, max_facets: int = 4):
        self.calls.append(question)
        raise AssertionError("provider must not be called")


def test_one_entity_two_attributes_becomes_two_facets() -> None:
    plan = plan_evidence_facets("find the username and password for node-17")
    assert plan.route == "deterministic"
    assert len(plan.facets) == 2
    assert [facet.index for facet in plan.facets] == [0, 1]
    assert [facet.attributes for facet in plan.facets] == [
        ("username",),
        ("password",),
    ]
    assert all("node-17" in facet.query for facet in plan.facets)


def test_two_entities_requesting_same_attribute_remain_distinct() -> None:
    plan = plan_evidence_facets(
        "find the username for node-17 and the username for node-18"
    )
    assert len(plan.facets) == 2
    assert "node-17" in plan.facets[0].query
    assert "node-18" in plan.facets[1].query


def test_explicit_independent_clauses_split_in_original_order() -> None:
    plan = plan_evidence_facets(
        "find the username for node-17 and list the password for node-18"
    )
    assert len(plan.facets) == 2
    assert "node-17" in plan.facets[0].query
    assert "node-18" in plan.facets[1].query


def test_prose_with_and_but_single_request_does_not_split() -> None:
    plan = plan_evidence_facets("What is the Rock and Roll policy for node-17?")
    assert len(plan.facets) == 1
    assert plan.facets[0].query == "What is the Rock and Roll policy for node-17?"
    assert plan.route == "single"


def test_table_title_with_and_does_not_false_split() -> None:
    plan = plan_evidence_facets("list all rows in the Alpha and Beta inventory table")
    assert len(plan.facets) == 1


def test_blank_question_returns_single_facet() -> None:
    plan = plan_evidence_facets("   ")
    assert len(plan.facets) == 1
    assert plan.fallback_reason == "empty_question"


def test_oversized_question_returns_single_facet() -> None:
    plan = plan_evidence_facets("x" * 2001)
    assert len(plan.facets) == 1
    assert plan.fallback_reason == "oversized_question"


def test_planner_failure_degrades_to_fallback_without_raising() -> None:
    plan = plan_evidence_facets(
        "find the username for node-17 and the current status",
        planner_provider=RaisingPlanner(),
    )
    assert len(plan.facets) == 1
    assert plan.route == "fallback"
    assert plan.fallback_reason == "planner_error"


def test_single_fact_question_never_calls_provider() -> None:
    spy = SpyPlanner()
    plan = plan_evidence_facets("what is escalation", planner_provider=spy)
    assert len(plan.facets) == 1
    assert plan.route == "single"
    assert spy.calls == []


def test_round4a_compound_full_table_plan_skips_generic_provider() -> None:
    spy = SpyPlanner()
    plan = plan_evidence_facets(
        "列出 Alpha Inventory 表格中的所有 server和列出 Beta Access table 的所有行",
        planner_provider=spy,
    )
    assert len(plan.facets) == 1
    assert plan.fallback_reason == "full_table_route"
    assert spy.calls == []


def test_deterministic_path_does_not_call_provider() -> None:
    spy = SpyPlanner()
    plan = plan_evidence_facets(
        "find the username and password for node-17",
        planner_provider=spy,
    )
    assert plan.route == "deterministic"
    assert spy.calls == []


def test_ambiguous_multiword_attribute_reaches_structured_provider() -> None:
    class Provider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def plan(self, question: str, max_facets: int = 4):
            self.calls.append(question)
            return EvidenceQueryPlan(
                original_query=question,
                facets=(
                    EvidenceFacet(
                        index=0,
                        query="user name node17",
                        entities=(QueryEntity("node17", "node17"),),
                        attributes=("user name",),
                    ),
                    EvidenceFacet(
                        index=1,
                        query="password node17",
                        entities=(QueryEntity("node17", "node17"),),
                        attributes=("password",),
                    ),
                ),
                route="structured",
                confidence=0.9,
            )

    provider = Provider()
    plan = plan_evidence_facets(
        "find the user name and password for node17",
        planner_provider=provider,
    )

    assert provider.calls == ["find the user name and password for node17"]
    assert plan.route == "structured"
    assert [facet.query for facet in plan.facets] == [
        "user name node17",
        "password node17",
    ]
    assert [facet.attributes for facet in plan.facets] == [("user name",), ("password",)]
    assert [facet.entities[0].text for facet in plan.facets] == ["node17", "node17"]


def test_metadata_is_redacted_for_deterministic_plan() -> None:
    plan = plan_evidence_facets("find the username and password for node-17")
    metadata = plan.to_metadata()
    assert "node-17" not in str(metadata)
    assert "username" not in str(metadata)
    assert metadata["facet_count"] == 2
    assert metadata["facet_indexes"] == [0, 1]
