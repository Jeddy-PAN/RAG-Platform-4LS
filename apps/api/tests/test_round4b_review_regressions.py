"""Regression tests for the Round 4B review findings."""

import json
import uuid

from app.rag.prompting import build_chat_prompt
from app.rag.retrieval.evidence_selection import select_evidence_facets
from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    FacetAssessment,
    FacetEvidenceCoverage,
    EvidenceSelectionPlan,
    QueryEntity,
)
from app.rag.retrieval.types import RetrievalCandidate


def _candidate(
    text: str,
    *,
    fused_score: float,
    chunk_id: uuid.UUID | None = None,
    score_metadata: dict | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="synthetic-source.txt",
        chunk_index=0,
        text=text,
        source_metadata={},
        fused_score=fused_score,
        score_metadata=score_metadata or {},
    )


def _facet_plan(*queries: str) -> EvidenceQueryPlan:
    return EvidenceQueryPlan(
        original_query="synthetic compound question",
        facets=tuple(
            EvidenceFacet(
                index=index,
                query=query,
                entities=(QueryEntity(text="entity-17", normalized="entity-17"),),
                attributes=(query.split()[0],),
            )
            for index, query in enumerate(queries)
        ),
        route="deterministic",
        confidence=0.6,
    )


def test_entity_only_candidate_does_not_cover_requested_attribute() -> None:
    plan = _facet_plan("attribute-a entity-17")
    entity_only = _candidate("entity-17 maintenance note", fused_score=0.9)

    _, selection = select_evidence_facets(
        plan,
        {0: [entity_only]},
        top_k=1,
    )

    assert selection.coverage[0].status == "unresolved"
    assert selection.coverage[0].reason == "no_supporting_evidence"


def test_wrong_attribute_does_not_cover_requested_facet() -> None:
    plan = _facet_plan("attribute-a entity-17")
    wrong_attribute = _candidate("entity-17 attribute-b note", fused_score=0.9)

    _, selection = select_evidence_facets(
        plan,
        {0: [wrong_attribute]},
        top_k=1,
    )

    assert selection.coverage[0].status == "unresolved"


def test_correct_attribute_outranks_high_scoring_entity_only_candidate() -> None:
    plan = _facet_plan("attribute-a entity-17")
    entity_only = _candidate("entity-17 maintenance note", fused_score=0.95)
    correct = _candidate("entity-17 attribute-a note", fused_score=0.25)

    selected, selection = select_evidence_facets(
        plan,
        {0: [entity_only, correct]},
        top_k=1,
    )

    assert [candidate.chunk_id for candidate in selected] == [correct.chunk_id]
    assert selection.coverage[0].status == "covered"


def test_duplicate_chunk_ids_consume_one_slot_and_keep_union_membership() -> None:
    plan = _facet_plan("attribute-a entity-17", "attribute-b entity-17")
    first = _candidate("entity-17 attribute-a fact", fused_score=0.9)
    second = _candidate("entity-17 attribute-b fact", fused_score=0.8)
    shared_id = uuid.uuid4()
    shared_first = _candidate("unrelated shared context", fused_score=0.1, chunk_id=shared_id)
    shared_second = _candidate("unrelated shared context", fused_score=0.05, chunk_id=shared_id)

    selected, selection = select_evidence_facets(
        plan,
        {0: [first, shared_first], 1: [second, shared_second]},
        top_k=4,
    )

    assert len(selected) == len({candidate.chunk_id for candidate in selected})
    shared = next(candidate for candidate in selected if candidate.chunk_id == shared_id)
    assert shared.score_metadata["evidence_facet_indexes"] == [0, 1]
    assert all(coverage.status == "covered" for coverage in selection.coverage)


def test_conflict_with_insufficient_budget_is_not_marked_fully_evidenced() -> None:
    plan = _facet_plan("attribute-a entity-17")
    first = _candidate("entity-17 attribute-a claim-one", fused_score=0.9)
    second = _candidate("entity-17 attribute-a claim-two", fused_score=0.8)

    class Assessor:
        def assess(self, plan, facet_index, candidates):
            return FacetAssessment(
                facet_index=facet_index,
                supporting_chunk_ids=(first.chunk_id, second.chunk_id),
                conflict_groups=((first.chunk_id,), (second.chunk_id,)),
            )

    _, selection = select_evidence_facets(
        plan,
        {0: [first, second]},
        top_k=1,
        assessor=Assessor(),
    )

    assert selection.coverage[0].status == "unresolved"
    assert selection.coverage[0].reason == "budget_exhausted"
    assert selection.coverage[0].selected_chunk_ids == ()


def test_base_support_is_reserved_before_conflict_extras() -> None:
    plan = _facet_plan("attribute-a entity-17", "attribute-b entity-17")
    first = _candidate("entity-17 attribute-a claim-one", fused_score=0.9)
    second = _candidate("entity-17 attribute-a claim-two", fused_score=0.8)
    other = _candidate("entity-17 attribute-b fact", fused_score=0.2)

    class Assessor:
        def assess(self, plan, facet_index, candidates):
            if facet_index == 0:
                return FacetAssessment(
                    facet_index=0,
                    supporting_chunk_ids=(first.chunk_id, second.chunk_id),
                    conflict_groups=((first.chunk_id,), (second.chunk_id,)),
                )
            return FacetAssessment(
                facet_index=1,
                supporting_chunk_ids=(other.chunk_id,),
            )

    selected, selection = select_evidence_facets(
        plan,
        {0: [first, second], 1: [other]},
        top_k=2,
        assessor=Assessor(),
    )

    assert {candidate.chunk_id for candidate in selected} == {
        first.chunk_id,
        other.chunk_id,
    }
    assert selection.coverage[0].status == "unresolved"
    assert selection.coverage[0].reason == "budget_exhausted"
    assert selection.coverage[1].status == "covered"


def test_cjk_attribute_support_is_boundary_independent_without_assessor() -> None:
    plan = EvidenceQueryPlan(
        original_query="synthetic Chinese attribute question",
        facets=(
            EvidenceFacet(
                index=0,
                query="服务器用户名 node17",
                entities=(QueryEntity("node17", "node17"),),
                attributes=("服务器用户名",),
            ),
        ),
        route="fallback",
        confidence=0.0,
    )
    candidates = [
        _candidate("node17 服务器用户名 alpha", fused_score=0.9),
        _candidate("node17，服务器用户名：alpha", fused_score=0.8),
        _candidate("node17的服务器用户名为alpha", fused_score=0.7),
    ]

    _, selection = select_evidence_facets(plan, {0: candidates}, top_k=3)

    assert selection.coverage[0].status == "covered"
    assert len(selection.coverage[0].selected_chunk_ids) == 3


def test_wrong_facet_assessment_is_rejected() -> None:
    plan = _facet_plan("attribute-a entity-17")
    candidate = _candidate("entity-17 attribute-a claim", fused_score=0.9)

    class Assessor:
        def assess(self, plan, facet_index, candidates):
            return FacetAssessment(
                facet_index=facet_index + 1,
                supporting_chunk_ids=(candidate.chunk_id,),
                conflict_groups=((candidate.chunk_id,), (candidate.chunk_id,)),
            )

    _, selection = select_evidence_facets(
        plan,
        {0: [candidate]},
        top_k=1,
        assessor=Assessor(),
    )

    assert selection.coverage[0].status == "covered"


def test_generic_prompt_names_each_facet_and_allowed_sources() -> None:
    first = _candidate("entity-17 attribute-a fact", fused_score=0.9)
    second = _candidate("entity-17 attribute-b fact", fused_score=0.8)
    plan = EvidenceQueryPlan(
        original_query="synthetic compound question",
        facets=(
            EvidenceFacet(
                index=0,
                query="attribute-a entity-17",
                entities=(QueryEntity("entity-17", "entity-17"),),
                attributes=("attribute-a",),
            ),
            EvidenceFacet(
                index=1,
                query="attribute-b entity-17",
                entities=(QueryEntity("entity-17", "entity-17"),),
                attributes=("attribute-b",),
            ),
        ),
        route="deterministic",
        confidence=0.6,
    )
    selection = EvidenceSelectionPlan(
        query_plan=plan,
        coverage=(
            FacetEvidenceCoverage(
                facet_index=0,
                status="covered",
                selected_chunk_ids=(first.chunk_id,),
            ),
            FacetEvidenceCoverage(
                facet_index=1,
                status="unresolved",
                reason="no_supporting_evidence",
            ),
        ),
    )

    prompt = build_chat_prompt(
        question="synthetic compound question",
        retrieved_chunks=[first, second],
        recent_messages=[],
        evidence_selection_plan=selection,
    )
    system_content = prompt.messages[0]["content"]

    assert "attribute-a entity-17" in system_content
    assert "attribute-b entity-17" in system_content
    assert "[Source 1]" in system_content


def test_generic_prompt_refuses_invalid_covered_source_mapping() -> None:
    candidate = _candidate("entity-17 attribute-a fact", fused_score=0.9)
    selection = EvidenceSelectionPlan(
        query_plan=_facet_plan("attribute-a entity-17"),
        coverage=(
            FacetEvidenceCoverage(
                facet_index=0,
                status="covered",
                selected_chunk_ids=(uuid.uuid4(),),
            ),
        ),
    )

    prompt = build_chat_prompt(
        question="synthetic compound question",
        retrieved_chunks=[candidate],
        recent_messages=[],
        evidence_selection_plan=selection,
    )

    assert prompt.should_refuse is True


def test_generic_prompt_refuses_source_mapped_only_to_another_facet() -> None:
    candidate = _candidate(
        "entity-17 attribute-a fact",
        fused_score=0.9,
        score_metadata={"evidence_facet_indexes": [1]},
    )
    selection = EvidenceSelectionPlan(
        query_plan=_facet_plan("attribute-a entity-17", "attribute-b entity-17"),
        coverage=(
            FacetEvidenceCoverage(
                facet_index=0,
                status="covered",
                selected_chunk_ids=(candidate.chunk_id,),
            ),
            FacetEvidenceCoverage(facet_index=1, status="unresolved"),
        ),
    )

    prompt = build_chat_prompt(
        question="synthetic compound question",
        retrieved_chunks=[candidate],
        recent_messages=[],
        evidence_selection_plan=selection,
    )

    assert prompt.should_refuse is True


def test_structured_planner_preserves_multiword_grounded_attributes() -> None:
    from app.rag.providers.query_planner import OpenAIFacetPlannerProvider
    from app.rag.providers.chat import ChatProviderResult

    content = json.dumps(
        {
            "facets": [
                {
                    "index": 0,
                    "query": "current deployment status for entity-17",
                    "entity": "entity-17",
                    "attribute": "current deployment status",
                },
                {
                    "index": 1,
                    "query": "access policy for entity-17",
                    "entity": "entity-17",
                    "attribute": "access policy",
                },
            ]
        }
    )

    class Provider:
        def generate_chat_completion(self, messages, temperature=0.1):
            return ChatProviderResult(content=content, model="synthetic")

    plan = OpenAIFacetPlannerProvider(chat_provider=Provider()).plan(
        "find the current deployment status and access policy for entity-17"
    )

    assert [facet.attributes for facet in plan.facets] == [
        ("current deployment status",),
        ("access policy",),
    ]


def test_planner_configuration_failure_has_a_distinct_fallback_reason(
    monkeypatch,
) -> None:
    from app.core.config import Settings
    from app.rag.providers.query_planner import OpenAIFacetPlannerProvider
    from app.rag.retrieval.evidence_facets import plan_evidence_facets

    monkeypatch.setattr(
        "app.rag.providers.query_planner.get_settings",
        lambda: Settings(llm_api_key=""),
    )

    plan = plan_evidence_facets(
        "请查找 entity-17 的 attribute-a 和 attribute-b",
        planner_provider=OpenAIFacetPlannerProvider(),
    )

    assert plan.route == "fallback"
    assert plan.fallback_reason == "planner_configuration"


def test_round4b_factory_exposes_lazy_planner_and_assessor() -> None:
    from app.core.config import Settings
    from app.rag.providers.query_planner import OpenAIFacetPlannerProvider
    from app.rag.providers.round4b import (
        OpenAIFacetEvidenceAssessor,
        get_round4b_providers,
    )

    providers = get_round4b_providers(
        Settings(
            llm_base_url="https://provider.invalid/v1",
            llm_api_key="synthetic-key",
            llm_model="synthetic-model",
        )
    )

    assert isinstance(providers.planner_provider, OpenAIFacetPlannerProvider)
    assert isinstance(providers.evidence_assessor, OpenAIFacetEvidenceAssessor)


def test_assessor_response_parser_accepts_only_grounded_chunk_ids() -> None:
    from app.rag.providers.round4b import _parse_assessment_response

    first = uuid.uuid4()
    second = uuid.uuid4()
    response = json.dumps(
        {
            "facet_index": 0,
            "supporting_chunk_ids": [str(first), str(second)],
            "conflict_groups": [[str(first)], [str(second)]],
        }
    )

    assessment = _parse_assessment_response(
        response,
        facet_index=0,
        candidate_ids={first, second},
    )

    assert assessment.facet_index == 0
    assert assessment.supporting_chunk_ids == (first, second)
    assert assessment.conflict_groups == ((first,), (second,))


def test_assessor_response_parser_rejects_extra_keys_and_unknown_ids() -> None:
    import pytest

    from app.rag.providers.round4b import (
        AssessorProviderError,
        _parse_assessment_response,
    )

    known = uuid.uuid4()
    unknown = uuid.uuid4()
    response = json.dumps(
        {
            "facet_index": 0,
            "supporting_chunk_ids": [str(known), str(unknown)],
            "conflict_groups": [],
            "values": ["must not be returned"],
        }
    )

    with pytest.raises(AssessorProviderError):
        _parse_assessment_response(
            response,
            facet_index=0,
            candidate_ids={known},
        )


def test_chat_injects_round4b_providers_for_structured_question(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus
    from app.models.project import Project
    from app.rag.providers.chat import ChatProviderResult
    from app.rag.providers.round4b import Round4BProviderBundle

    with sqlite_session_factory() as db:
        project = Project(name=f"round4b-chat-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="synthetic-facts.txt",
            storage_path="/tmp/synthetic-facts.txt",
            file_size_bytes=100,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        for index, text in enumerate(
            ("entity-17 attribute-a fact", "entity-17 attribute-b fact")
        ):
            db.add(
                Chunk(
                    project_id=project.id,
                    document_id=document.id,
                    chunk_index=index,
                    text=text,
                    content_hash=str(uuid.uuid4()),
                )
            )
        db.commit()
        project_id = project.id

    planner_calls: list[str] = []
    assessor_calls: list[int] = []

    class Planner:
        def plan(self, question, max_facets=4):
            planner_calls.append(question)
            return EvidenceQueryPlan(
                original_query=question,
                facets=(
                    EvidenceFacet(
                        index=0,
                        query="attribute-a entity-17",
                        entities=(QueryEntity("entity-17", "entity-17"),),
                        attributes=("attribute-a",),
                    ),
                    EvidenceFacet(
                        index=1,
                        query="attribute-b entity-17",
                        entities=(QueryEntity("entity-17", "entity-17"),),
                        attributes=("attribute-b",),
                    ),
                ),
                route="structured",
                confidence=0.7,
            )

    class Assessor:
        def assess(self, plan, facet_index, candidates):
            assessor_calls.append(facet_index)
            return FacetAssessment(facet_index=facet_index)

    class AnswerProvider:
        def generate_chat_completion(self, messages, temperature=0.1):
            return ChatProviderResult(content="synthetic answer", model="synthetic")

    monkeypatch.setattr(
        "app.rag.chat_service.get_round4b_providers",
        lambda: Round4BProviderBundle(Planner(), Assessor()),
        raising=False,
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: AnswerProvider(),
    )

    response = api_client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={
            "message": "请查找 entity-17 的 attribute-a 和 attribute-b",
            "retrieval": {"mode": "keyword", "top_k": 4},
        },
    )

    assert response.status_code == 200
    assert planner_calls == ["请查找 entity-17 的 attribute-a 和 attribute-b"]
    assert assessor_calls == [0, 1]


def test_eval_injects_the_same_round4b_provider_policy(
    api_client,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus
    from app.models.project import Project
    from app.rag.providers.chat import ChatProviderResult
    from app.rag.providers.round4b import Round4BProviderBundle

    with sqlite_session_factory() as db:
        project = Project(name=f"round4b-eval-{uuid.uuid4()}")
        db.add(project)
        db.flush()
        document = Document(
            project_id=project.id,
            filename="synthetic-eval.txt",
            storage_path="/tmp/synthetic-eval.txt",
            file_size_bytes=100,
            status=DocumentStatus.indexed,
        )
        db.add(document)
        db.flush()
        db.add(
            Chunk(
                project_id=project.id,
                document_id=document.id,
                chunk_index=0,
                text="entity-17 attribute-a fact",
                content_hash=str(uuid.uuid4()),
            )
        )
        db.commit()
        project_id = project.id

    planner_calls: list[str] = []

    class Planner:
        def plan(self, question, max_facets=4):
            planner_calls.append(question)
            return EvidenceQueryPlan(
                original_query=question,
                facets=(
                    EvidenceFacet(
                        index=0,
                        query="attribute-a entity-17",
                        entities=(QueryEntity("entity-17", "entity-17"),),
                        attributes=("attribute-a",),
                    ),
                ),
                route="structured",
                confidence=0.7,
            )

    class Assessor:
        def assess(self, plan, facet_index, candidates):
            return FacetAssessment(facet_index=facet_index)

    class AnswerProvider:
        def generate_chat_completion(self, messages, temperature=0.1):
            return ChatProviderResult(content="synthetic answer", model="synthetic")

    monkeypatch.setattr(
        "app.services.eval.get_round4b_providers",
        lambda: Round4BProviderBundle(Planner(), Assessor()),
        raising=False,
    )
    monkeypatch.setattr(
        "app.rag.answering.OpenAIChatProvider.from_settings",
        lambda: AnswerProvider(),
    )

    dataset = api_client.post(
        f"/api/projects/{project_id}/eval/datasets",
        json={"name": "Synthetic Round 4B"},
    ).json()
    api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/questions",
        json={
            "question": "请查找 entity-17 的 attribute-a 和 attribute-b",
            "should_answer": True,
        },
    )
    response = api_client.post(
        f"/api/projects/{project_id}/eval/datasets/{dataset['id']}/runs",
        json={"retrieval_mode": "keyword", "top_k": 4},
    )

    assert response.status_code == 201
    assert planner_calls == ["请查找 entity-17 的 attribute-a 和 attribute-b"]
