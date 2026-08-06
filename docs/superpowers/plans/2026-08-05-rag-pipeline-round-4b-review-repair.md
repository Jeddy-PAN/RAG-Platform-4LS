# RAG Pipeline Round 4B Review Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the five defects identified in the Round 4B review while preserving Round 4A table retrieval, ordinary single-facet retrieval, project/document isolation, and redacted metadata.

**Architecture:** Keep deterministic planning first and add one lazy production boundary that supplies the existing OpenAI-compatible chat transport to the structured facet planner and bounded evidence assessor. Merge generic candidates by chunk ID before facet reservation, derive coverage from facet-specific support signals, and let only validated assessor output create a fully evidenced conflict state. Bind each runtime facet query to its selected source numbers in the prompt while continuing to serialize only redacted selection metadata.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest, existing OpenAI-compatible chat provider, immutable Round 4B dataclasses.

---

### Task 1: Lock the review counterexamples with failing tests

**Files:**
- Create: `apps/api/tests/test_round4b_review_regressions.py`
- Modify: `apps/api/tests/test_evidence_facets.py`
- Modify: `apps/api/tests/test_evidence_selection.py`
- Modify: `apps/api/tests/test_prompting.py`
- Modify: `apps/api/tests/test_chat_api.py`
- Modify: `apps/api/tests/test_eval_api.py`

- [ ] Add tests showing that Chinese possessive compound questions and multiword attributes invoke the injected structured planner, while table plans and clear single-fact questions do not.
- [ ] Add tests showing entity-only and wrong-attribute candidates remain unresolved, while correct entity-plus-attribute support is preferred and both direct keyword metadata key forms are recognized.
- [ ] Add tests showing repeated candidate objects with one chunk ID produce one selected result and retain all facet memberships.
- [ ] Add tests showing malformed, wrong-facet, unknown-ID, empty, duplicate, and overlapping assessor groups are rejected, and a valid conflict reserves one final chunk per group.
- [ ] Add tests showing each prompt facet includes its runtime query and only its selected source numbers; invalid covered mappings become conservative instead of emitting an empty covered mapping.
- [ ] Run the new tests and record the expected failures before editing production code.

### Task 2: Wire the production planner and assessor boundary

**Files:**
- Create or modify: `apps/api/app/rag/providers/round4b.py`
- Modify: `apps/api/app/rag/providers/query_planner.py`
- Modify: `apps/api/app/rag/providers/types.py`
- Modify: `apps/api/app/rag/retrieval/evidence_facets.py`
- Modify: `apps/api/app/rag/retrieval/service.py`
- Modify: `apps/api/app/rag/chat_service.py`
- Modify: `apps/api/app/services/eval.py`
- Test: `apps/api/tests/test_round4b_review_regressions.py`

- [ ] Provide lazy factories for the structured planner and evidence assessor using the configured chat transport; do not construct or call them for accepted Round 4A or deterministic single-facet requests.
- [ ] Implement the assessor's strict JSON-only response boundary with bounded candidate snippets, no extracted values in the returned object, and provider/schema failures converted to a non-raising unavailable result.
- [ ] Keep planner input limited to the current question, expand only generic syntax activation for Chinese possessives and multiword attributes, and preserve original-query fallback with a redacted reason code for configuration/provider failure.
- [ ] Inject the same provider policy through chat and eval retrieval calls, while keeping direct `run_retrieval()` injection available for tests.
- [ ] Run planner, service, chat, and eval focused tests.

### Task 3: Correct facet support and canonical candidate merging

**Files:**
- Modify: `apps/api/app/rag/retrieval/evidence_selection.py`
- Modify: `apps/api/app/rag/retrieval/service.py`
- Test: `apps/api/tests/test_round4b_review_regressions.py`
- Test: `apps/api/tests/test_evidence_selection.py`

- [ ] Normalize entity, attribute, identifier, lexical-overlap, structure, and rank signals separately; require facet-specific attribute/subquestion evidence before deterministic coverage is `covered`.
- [ ] Read both direct keyword and namespaced score metadata keys through one helper.
- [ ] Merge all facet candidate pools by chunk ID before structural deduplication and selection, preserving best route scores, stable fields, and the union of facet indexes.
- [ ] Recheck selected IDs during every reservation and fill phase, preserve deterministic order, and keep the final count bounded by `top_k`.
- [ ] Run evidence-selection and facet-retrieval focused tests.

### Task 4: Make conflict assessment operational and budget-safe

**Files:**
- Modify: `apps/api/app/rag/retrieval/evidence_selection.py`
- Modify: `apps/api/app/rag/retrieval/evidence_types.py`
- Modify: `apps/api/app/rag/providers/round4b.py`
- Test: `apps/api/tests/test_round4b_review_regressions.py`
- Test: `apps/api/tests/test_evidence_query_types.py`

- [ ] Validate assessor facet identity, candidate ownership, non-empty groups, distinct/disjoint groups, and supporting-ID membership.
- [ ] Reserve at least one final candidate from every valid conflict group before assigning `conflicting`; if the global budget cannot retain all groups, mark the facet unresolved with an explicit budget reason.
- [ ] On timeout, provider, or schema failure, use deterministic support selection with `assessment_unavailable` and never create a false conflict or server error.
- [ ] Persist only chunk IDs, groups, statuses, and reason codes through the existing redacted serializers.
- [ ] Run all conflict and metadata focused tests.

### Task 5: Bind facet identity and source ownership in prompts

**Files:**
- Modify: `apps/api/app/rag/prompting.py`
- Modify: `apps/api/app/rag/answering.py`
- Modify: `apps/api/app/rag/chat_service.py`
- Modify: `apps/api/app/services/eval.py`
- Test: `apps/api/tests/test_prompting.py`
- Test: `apps/api/tests/test_answer_generation.py`
- Test: `apps/api/tests/test_chat_api.py`
- Test: `apps/api/tests/test_eval_api.py`

- [ ] Build a facet-index lookup from the query plan and include each facet's runtime query, terminal status, and allowed source numbers in the prompt.
- [ ] Refuse or downgrade invalid facet/source mappings before model invocation; keep partial coverage generative and all-unresolved coverage locally refused.
- [ ] Render each valid conflict group only with final selected sources and keep groups separate.
- [ ] Preserve Round 4A prompt and clarification behavior and keep assistant metadata redacted.
- [ ] Run prompt, answer, chat, eval, and retrieval-log tests.

### Task 6: Regression verification and handoff

**Files:**
- Modify only focused implementation/tests if verification exposes a defect.

- [ ] Run all new and changed Round 4B tests together with ordinary evidence, retrieval, prompting, answer, chat, eval, table-facet, and table-expansion tests touched by the call paths.
- [ ] Run `python -m compileall app` and `git diff --check` from `apps/api`/repository root as appropriate.
- [ ] Inspect metadata assertions for absence of raw facet queries, entity/attribute text, source text, `search_text`, and extracted values.
- [ ] Report exact test counts, mocked versus live planner/assessor calls, tests not run, deviations, and remaining PostgreSQL/live-provider acceptance work.
