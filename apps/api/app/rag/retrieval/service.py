import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.retrieval import RetrievalMode
from app.rag.providers.embeddings import (
    EmbeddingProviderError,
    get_embedding_provider_from_settings,
)
from app.rag.providers.types import (
    EmbeddingProvider,
    FacetEvidenceAssessor,
    QueryFacetPlannerProvider,
)
from app.rag.providers.reranking import get_reranker_provider_from_settings
from app.rag.retrieval.evidence_facets import plan_evidence_facets
from app.rag.retrieval.evidence_selection import select_evidence, select_evidence_facets
from app.rag.retrieval.evidence_types import EvidenceQueryPlan, EvidenceSelectionPlan
from app.rag.retrieval.hybrid import fuse_retrieval_results
from app.rag.retrieval.keyword import retrieve_keyword
from app.rag.retrieval.query_facets import plan_table_query
from app.rag.retrieval.rerankers import (
    RerankerProvider,
    RerankerProviderError,
    RerankOutcome,
    rerank_with_fallback,
)
from app.rag.retrieval.types import (
    FacetTableContextCoverage,
    RetrievalCandidate,
    RetrievalResult,
    TableContextCoverage,
    TableFacetOutcome,
    TableSelectionCandidate,
    TableSelectionOutcome,
    TableSelectionPlan,
)
from app.rag.retrieval.vector import retrieve_vector
from app.services.retrieval_logs import create_retrieval_log


def _retrieve_query_candidates(
    db: Session,
    *,
    project_id: uuid.UUID,
    query: str,
    mode: RetrievalMode,
    candidate_limit: int,
    vector_weight: float,
    keyword_weight: float,
    similarity_threshold: float,
    document_id: uuid.UUID | None,
    query_embedding: list[float] | None,
) -> list[RetrievalCandidate]:
    if mode == RetrievalMode.keyword:
        return retrieve_keyword(
            db,
            project_id,
            query,
            candidate_limit,
            document_id=document_id,
        )
    if query_embedding is None:
        raise ValueError("query_embedding is required for vector and hybrid retrieval")
    if mode == RetrievalMode.vector:
        return retrieve_vector(
            db,
            project_id,
            query_embedding,
            candidate_limit,
            similarity_threshold=similarity_threshold,
            document_id=document_id,
        )

    vector_results = retrieve_vector(
        db,
        project_id,
        query_embedding,
        candidate_limit,
        similarity_threshold=similarity_threshold,
        document_id=document_id,
    )
    keyword_results = retrieve_keyword(
        db,
        project_id,
        query,
        candidate_limit,
        document_id=document_id,
    )
    return fuse_retrieval_results(
        vector_results,
        keyword_results,
        top_k=candidate_limit,
        vector_weight=vector_weight,
        keyword_weight=keyword_weight,
    )


def _retrieve_facet_candidates(
    db: Session,
    *,
    project_id: uuid.UUID,
    evidence_plan: EvidenceQueryPlan,
    mode: RetrievalMode,
    candidate_limit: int,
    vector_weight: float,
    keyword_weight: float,
    similarity_threshold: float,
    document_id: uuid.UUID | None,
    embedding_provider: EmbeddingProvider | None,
) -> dict[int, list[RetrievalCandidate]]:
    """Retrieve ordinary candidates independently for every evidence facet.

    In vector/hybrid modes all facet queries are embedded in one batched call;
    keyword mode never requests embeddings. Project and optional document scope
    are applied to every route.
    """
    facet_queries = [facet.query for facet in evidence_plan.facets]
    if mode == RetrievalMode.keyword:
        facet_embeddings: list[list[float] | None] = [None] * len(facet_queries)
    else:
        provider = embedding_provider or get_embedding_provider_from_settings()
        facet_embeddings = provider.embed_texts(facet_queries)

    candidates_by_facet: dict[int, list[RetrievalCandidate]] = {}
    for facet, facet_embedding in zip(evidence_plan.facets, facet_embeddings):
        candidates_by_facet[facet.index] = _retrieve_query_candidates(
            db,
            project_id=project_id,
            query=facet.query,
            mode=mode,
            candidate_limit=candidate_limit,
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
            similarity_threshold=similarity_threshold,
            document_id=document_id,
            query_embedding=facet_embedding,
        )
    return candidates_by_facet


class _CountingFacetAssessor:
    """Count bounded assessor calls without recording request or response bodies."""

    def __init__(self, assessor: FacetEvidenceAssessor) -> None:
        self.assessor = assessor
        self.calls = 0

    def assess(self, plan, facet_index: int, candidates):
        self.calls += 1
        return self.assessor.assess(plan, facet_index, candidates)


def run_retrieval(
    db: Session,
    project_id: uuid.UUID,
    query: str,
    mode: RetrievalMode,
    top_k: int,
    vector_weight: float = 0.65,
    keyword_weight: float = 0.35,
    similarity_threshold: float = 0.0,
    embedding_provider: EmbeddingProvider | None = None,
    reranker_enabled: bool = False,
    reranker_candidate_limit: int = 40,
    document_id: uuid.UUID | None = None,
    preferred_document_id: uuid.UUID | None = None,
    preferred_table_index: int | None = None,
    preferred_tables_by_facet: dict[int, tuple[uuid.UUID, int]] | None = None,
    planner_provider: QueryFacetPlannerProvider | None = None,
    evidence_assessor: FacetEvidenceAssessor | None = None,
    reranker_provider: RerankerProvider | None = None,
) -> RetrievalResult:
    """Run project-scoped retrieval and persist debug logs.

    When *document_id* is provided, retrieval is scoped to that document.
    When a table-intent query is detected and table chunks are found in
    the initial results, same-table expansion loads the full table or
    row groups, and parent/child deduplication removes overlapping rows.

    Compound full-table queries are split into conservative facets, retrieved
    and selected per facet, and expanded under one shared context budget.
    Generic entity/attribute questions use the Round 4B evidence-facet route.
    """

    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    from app.rag.retrieval.table_expansion import (
        apply_context_budget,
        apply_multi_table_context_budget,
        dedup_parent_child,
        detect_table_intent,
        expand_same_table,
        expand_selected_table_groups,
        select_table_facets,
        select_target_table,
        summarize_table_context,
    )

    started = time.perf_counter()
    query_plan = plan_table_query(query)
    evidence_plan: EvidenceQueryPlan | None = None
    planner_latency_ms = 0
    planner_called = False
    evidence_selection_latency_ms = 0
    evidence_assessor_call_count = 0
    counting_assessor: _CountingFacetAssessor | None = None
    if not query_plan.is_compound:
        planner_started = time.perf_counter()
        evidence_plan = plan_evidence_facets(
            query,
            planner_provider=planner_provider,
        )
        planner_latency_ms = int((time.perf_counter() - planner_started) * 1000)
        planner_called = (
            planner_provider is not None
            and evidence_plan.route in {"structured", "fallback"}
            and evidence_plan.fallback_reason
            not in {"empty_question", "oversized_question", "full_table_route", "planner_unavailable"}
        )
    table_intent = False
    is_full_table = False
    expansion_applied = False
    selection_outcome: TableSelectionOutcome | None = None
    selection_plan: TableSelectionPlan | None = None
    table_contexts: list[FacetTableContextCoverage] = []
    evidence_selection_plan: EvidenceSelectionPlan | None = None
    evidence_selected = False
    context_partial = False
    table_context: TableContextCoverage | None = None
    reranker_outcomes: list[RerankOutcome] = []
    reranker_fallback_reason: str | None = None
    configured_reranker_name: str | None = None
    effective_reranker_limit = reranker_candidate_limit
    if reranker_enabled:
        from app.core.config import get_settings

        try:
            settings = get_settings()
            configured_reranker_name = settings.reranker_provider
            valid_request_limit = (
                isinstance(reranker_candidate_limit, int)
                and not isinstance(reranker_candidate_limit, bool)
                and reranker_candidate_limit > 0
            )
            valid_settings_limit = (
                isinstance(settings.reranker_candidate_limit, int)
                and not isinstance(settings.reranker_candidate_limit, bool)
                and settings.reranker_candidate_limit > 0
            )
            if not valid_request_limit or not valid_settings_limit:
                effective_reranker_limit = max(top_k, 1)
                reranker_provider = None
                reranker_fallback_reason = "configuration_invalid"
            else:
                effective_reranker_limit = min(
                    reranker_candidate_limit,
                    settings.reranker_candidate_limit,
                )
            if reranker_provider is None and reranker_fallback_reason is None:
                reranker_provider = get_reranker_provider_from_settings(settings)
        except (RerankerProviderError, ValueError, TypeError):
            if reranker_provider is None:
                reranker_provider = None
            reranker_fallback_reason = "configuration_invalid"
    initial_limit = max(top_k, effective_reranker_limit) if reranker_enabled else top_k

    def rerank_pool(
        query_text: str,
        pool: list[RetrievalCandidate],
        *,
        facet_index: int | None = None,
    ) -> list[RetrievalCandidate]:
        if not reranker_enabled or not pool:
            return pool
        if reranker_fallback_reason == "configuration_invalid":
            return pool
        bounded = pool[:effective_reranker_limit]
        outcome = rerank_with_fallback(
            query_text,
            bounded,
            top_k=len(bounded),
            provider=reranker_provider,
            facet_index=facet_index,
            fallback_reason_override=reranker_fallback_reason,
            provider_name_override=configured_reranker_name if reranker_fallback_reason else None,
        )
        reranker_outcomes.append(outcome)
        return outcome.results

    try:
        # ── Intent detection (before retrieval) ──
        table_intent, is_full_table = detect_table_intent(query)
        preferred_table = preferred_document_id is not None and preferred_table_index is not None
        if preferred_table:
            table_intent = True
            is_full_table = True
        if query_plan.is_compound:
            table_intent = True
            is_full_table = True

        # Wide candidate pool for full-table queries so the target table
        # does not need to enter the final top_k before selection.
        if is_full_table:
            wide_limit = max(top_k * 5, 40)
        else:
            wide_limit = initial_limit

        # Candidate limits are shared by the single-facet path and every
        # compound facet so the current route widths remain exact.
        if mode == RetrievalMode.keyword:
            candidate_limit = max(wide_limit, top_k * 3, 20)
        elif mode == RetrievalMode.vector:
            candidate_limit = wide_limit
        elif is_full_table:
            candidate_limit = max(wide_limit * 3, 60)
        else:
            candidate_limit = max(top_k * 3, 20, wide_limit)

        if query_plan.is_compound:
            # ── Batched facet retrieval ──
            facet_queries = [facet.query for facet in query_plan.facets]
            if mode == RetrievalMode.keyword:
                facet_embeddings: list[list[float] | None] = [None] * len(facet_queries)
            else:
                provider = embedding_provider or get_embedding_provider_from_settings()
                facet_embeddings = provider.embed_texts(facet_queries)

            candidates_by_facet: dict[int, list[RetrievalCandidate]] = {}
            for facet, facet_embedding in zip(query_plan.facets, facet_embeddings):
                facet_candidates = _retrieve_query_candidates(
                    db,
                    project_id=project_id,
                    query=facet.query,
                    mode=mode,
                    candidate_limit=candidate_limit,
                    vector_weight=vector_weight,
                    keyword_weight=keyword_weight,
                    similarity_threshold=similarity_threshold,
                    document_id=document_id,
                    query_embedding=facet_embedding,
                )
                for candidate in facet_candidates:
                    candidate.score_metadata = {
                        **(candidate.score_metadata or {}),
                        "table_facet_indexes": [facet.index],
                    }
                facet_candidates = rerank_pool(facet.query, facet_candidates, facet_index=facet.index)
                candidates_by_facet[facet.index] = facet_candidates

            selection_plan = select_table_facets(query_plan, candidates_by_facet)

            # Confirm preferred facet identities only when project-scoped
            # expansion actually returns chunks for that facet.
            if preferred_tables_by_facet:
                outcomes = list(selection_plan.outcomes)
                for facet_index, (pref_document_id, pref_table_index) in preferred_tables_by_facet.items():
                    if (
                        isinstance(facet_index, bool)
                        or not isinstance(facet_index, int)
                        or facet_index < 0
                        or facet_index >= len(outcomes)
                    ):
                        # Stale or corrupt pending index — leave the facet to
                        # its normal selection rather than raising a server error.
                        continue
                    validated: list[RetrievalCandidate] = []
                    if document_id is None or pref_document_id == document_id:
                        validated = expand_same_table(
                            db,
                            project_id,
                            pref_document_id,
                            pref_table_index,
                        )
                    if validated:
                        first = validated[0]
                        metadata = first.source_metadata or {}
                        outcomes[facet_index] = TableFacetOutcome(
                            facet=query_plan.facets[facet_index],
                            status="selected",
                            selected=TableSelectionCandidate(
                                document_id=pref_document_id,
                                document_name=first.document_name,
                                table_index=pref_table_index,
                                caption=metadata.get("caption"),
                                score=1.0,
                                score_breakdown={"conversation_confirmation": 1.0},
                            ),
                            reason="selected from recent clarification",
                        )
                    else:
                        outcomes[facet_index] = TableFacetOutcome(
                            facet=query_plan.facets[facet_index],
                            status="insufficient_score",
                            reason="confirmed table is no longer available",
                        )
                selection_plan = TableSelectionPlan(
                    original_query=selection_plan.original_query,
                    outcomes=outcomes,
                )

            # Expand distinct tables and apply the shared context budget.
            # Unresolved facets gate factual generation with empty results.
            if selection_plan.can_generate:
                groups = expand_selected_table_groups(db, project_id, selection_plan)
                results, table_contexts, context_partial = apply_multi_table_context_budget(
                    groups
                )
                expansion_applied = True
            else:
                results = []

        elif evidence_plan is not None and len(evidence_plan.facets) > 1:
            # ── Generic evidence-facet path (Round 4B) ──
            evidence_candidates_by_facet = _retrieve_facet_candidates(
                db,
                project_id=project_id,
                evidence_plan=evidence_plan,
                mode=mode,
                candidate_limit=candidate_limit,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
                similarity_threshold=similarity_threshold,
                document_id=document_id,
                embedding_provider=embedding_provider,
            )
            evidence_candidates_by_facet = {
                facet.index: rerank_pool(
                    facet.query,
                    evidence_candidates_by_facet.get(facet.index, []),
                    facet_index=facet.index,
                )
                for facet in evidence_plan.facets
            }
            selection_started = time.perf_counter()
            if evidence_assessor is not None:
                counting_assessor = _CountingFacetAssessor(evidence_assessor)
            results, evidence_selection_plan = select_evidence_facets(
                evidence_plan,
                evidence_candidates_by_facet,
                top_k=top_k,
                assessor=counting_assessor,
            )
            evidence_assessor_call_count = (
                counting_assessor.calls if counting_assessor is not None else 0
            )
            evidence_selection_latency_ms = int(
                (time.perf_counter() - selection_started) * 1000
            )
            evidence_selected = True

        else:
            # ── Single-facet compatibility path ──
            if mode == RetrievalMode.keyword:
                query_embedding = None
            else:
                provider = embedding_provider or get_embedding_provider_from_settings()
                query_embedding = provider.embed_texts([query])[0]

            results = _retrieve_query_candidates(
                db,
                project_id=project_id,
                query=query,
                mode=mode,
                candidate_limit=candidate_limit,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
                similarity_threshold=similarity_threshold,
                document_id=document_id,
                query_embedding=query_embedding,
            )
            results = rerank_pool(query, results)

            # ── Table-aware selection and expansion ──
            if is_full_table:
                expanded = None
                if preferred_table:
                    expanded = expand_same_table(
                        db,
                        project_id,
                        preferred_document_id,
                        preferred_table_index,
                    )
                    if expanded:
                        first = expanded[0]
                        metadata = first.source_metadata or {}
                        selected = TableSelectionCandidate(
                            document_id=preferred_document_id,
                            document_name=first.document_name,
                            table_index=preferred_table_index,
                            caption=metadata.get("caption"),
                            score=1.0,
                            score_breakdown={"conversation_confirmation": 1.0},
                        )
                        selection_outcome = TableSelectionOutcome(
                            status="selected",
                            selected=selected,
                            candidates=[selected],
                            reason="selected from recent clarification",
                        )
                    else:
                        selection_outcome = TableSelectionOutcome(
                            status="insufficient_score",
                            reason="confirmed table is no longer available",
                        )
                else:
                    selection_outcome = select_target_table(query, results)

                if selection_outcome.status == "selected" and selection_outcome.selected:
                    selected = selection_outcome.selected
                    expanded = expanded or expand_same_table(
                        db,
                        project_id,
                        selected.document_id,
                        selected.table_index,
                    )
                    if expanded:
                        non_table = [
                            candidate
                            for candidate in results
                            if (candidate.source_metadata or {}).get("table_chunk_type")
                            not in ("table", "table_group", "table_row", "table_header")
                            and candidate.document_id == selected.document_id
                        ]
                        results = dedup_parent_child(expanded + non_table)
                        results, context_partial = apply_context_budget(results)
                        expansion_applied = True
                    else:
                        selection_outcome = TableSelectionOutcome(
                            status="insufficient_score",
                            candidates=selection_outcome.candidates,
                            reason="selected table expansion returned no chunks",
                        )

                elif selection_outcome.status == "ambiguous":
                    pass

                else:  # "none" or "insufficient_score" — fall back to normal retrieval
                    pass

        # ── Final truncation ──
        if not expansion_applied and not evidence_selected:
            results = select_evidence(results, top_k=top_k)

        if expansion_applied and selection_outcome and selection_outcome.selected:
            table_context = summarize_table_context(results, selection_outcome.selected)
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    selection_metadata = None
    if selection_outcome is not None:
        selection_metadata = {
            "status": selection_outcome.status,
            "reason": selection_outcome.reason,
            "selected": (
                {
                    **selection_outcome.selected.identity_metadata(),
                    "score": selection_outcome.selected.score,
                    "score_breakdown": selection_outcome.selected.score_breakdown,
                }
                if selection_outcome.selected
                else None
            ),
            "candidates": [
                {
                    **candidate.identity_metadata(),
                    "score": candidate.score,
                    "score_breakdown": candidate.score_breakdown,
                }
                for candidate in selection_outcome.candidates
            ],
        }

    log_metadata = {
        "vector_weight": vector_weight,
        "keyword_weight": keyword_weight,
        "similarity_threshold": similarity_threshold,
        "reranker_enabled": reranker_enabled,
        "reranker": (
            reranker_outcomes[0].provider_name
            if reranker_outcomes
            else (configured_reranker_name if reranker_enabled else None)
        ),
        "reranker_candidate_limit": effective_reranker_limit if reranker_enabled else None,
        "reranker_candidate_count": sum(
            outcome.candidate_count for outcome in reranker_outcomes
        ) if reranker_enabled else 0,
        "reranker_latency_ms": sum(
            outcome.latency_ms for outcome in reranker_outcomes
        ) if reranker_enabled else 0,
        "reranker_fallback": any(
            outcome.fallback for outcome in reranker_outcomes
        ) or reranker_fallback_reason is not None,
        "reranker_fallback_reason": (
            reranker_fallback_reason
            or next(
                (outcome.fallback_reason for outcome in reranker_outcomes if outcome.fallback),
                None,
            )
        ),
        "table_intent": table_intent,
        "is_full_table": is_full_table,
        "expansion_applied": expansion_applied,
        "context_partial": context_partial,
        "evidence_selection": {
            "applied": not expansion_applied,
            "policy": "strong_lexical_then_ranked_fill" if not expansion_applied else None,
        },
    }
    if evidence_plan is not None:
        log_metadata["evidence_query_plan"] = evidence_plan.to_metadata()
        if evidence_selection_plan is not None:
            log_metadata["evidence_selection_plan"] = evidence_selection_plan.to_metadata()
        log_metadata["evidence_planner_latency_ms"] = planner_latency_ms
        log_metadata["evidence_planner_called"] = planner_called
        log_metadata["evidence_assessor_called"] = evidence_assessor_call_count > 0
        log_metadata["evidence_assessor_call_count"] = evidence_assessor_call_count
        log_metadata["evidence_selection_latency_ms"] = evidence_selection_latency_ms
    if query_plan.is_compound:
        selected_identities = {
            (outcome.selected.document_id, outcome.selected.table_index)
            for outcome in selection_plan.selected_outcomes
            if outcome.selected is not None
        }
        ambiguous_indexes = [
            outcome.facet.index
            for outcome in selection_plan.outcomes
            if outcome.status == "ambiguous"
        ]
        log_metadata["table_query_plan"] = {
            "is_compound": query_plan.is_compound,
            "facet_count": len(query_plan.facets),
            **selection_plan.to_metadata(),
            "distinct_selected_table_count": len(selected_identities),
            "table_contexts": [context.to_metadata() for context in table_contexts],
            "pending_clarification_index": (
                ambiguous_indexes[0] if ambiguous_indexes else None
            ),
        }
    else:
        log_metadata["table_context"] = table_context.to_metadata() if table_context else None
        log_metadata["table_selection"] = selection_metadata

    log = create_retrieval_log(
        db,
        project_id=project_id,
        query=query,
        mode=mode,
        top_k=top_k,
        latency_ms=latency_ms,
        results=results,
        metadata=log_metadata,
    )
    return RetrievalResult(
        query=query,
        mode=mode.value,
        top_k=top_k,
        latency_ms=latency_ms,
        results=results,
        retrieval_log_id=log.id,
        table_selection=selection_outcome,
        context_partial=context_partial,
        table_context=table_context,
        table_selection_plan=selection_plan,
        table_contexts=table_contexts,
        evidence_query_plan=evidence_plan,
        evidence_selection_plan=evidence_selection_plan,
    )
