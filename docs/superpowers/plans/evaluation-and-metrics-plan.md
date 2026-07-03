# Evaluation And Metrics Plan

> This is a lightweight module plan. It documents eval and metrics behavior without embedding full implementation code.

**Goal:** Provide project-scoped RAG evaluation and lightweight observability so retrieval quality, citation behavior, refusal behavior, judge quality, latency, and reranker changes can be measured locally.

**Current status:** The base eval system, optional LLM judge, reranker-aware eval runs, run compare, CSV/JSON export, and chat metrics dashboard are implemented.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, existing retrieval engine, existing chat orchestration, OpenAI-compatible judge provider, Next.js frontend, pytest.

---

## Scope

Implemented scope:

- eval dataset API
- eval question API
- synchronous eval run API
- project-scoped eval result persistence
- retrieval hit rate
- citation coverage
- refusal behavior
- answer match from expected notes
- optional LLM judge
- reranker-enabled eval runs
- eval run history and result filters
- multi-run compare
- CSV/JSON export helpers
- chat request metrics API
- metrics frontend page

Out of scope for the current version:

- scheduled eval runs
- async large-dataset eval execution
- token and cost accounting
- p50/p95 trend charts
- external observability tools such as Langfuse or Phoenix
- advanced statistical significance analysis

## File Areas

Backend:

- `apps/api/app/api/eval.py`
- `apps/api/app/api/metrics.py`
- `apps/api/app/schemas/eval.py`
- `apps/api/app/schemas/metrics.py`
- `apps/api/app/services/eval.py`
- `apps/api/app/services/eval_judge.py`
- `apps/api/app/services/metrics.py`
- `apps/api/app/models/eval.py`
- `apps/api/app/models/metrics.py`

Frontend:

- `apps/web/app/eval/page.tsx`
- `apps/web/app/metrics/page.tsx`
- `apps/web/components/eval-workspace.tsx`
- `apps/web/components/metrics-workspace.tsx`
- `apps/web/lib/eval-run-compare.ts`
- `apps/web/lib/eval-export.ts`
- `apps/web/lib/eval-result-filters.ts`

Tests:

- backend eval and metrics tests under `apps/api/tests`
- frontend helper tests under `apps/web/lib/*.test.mjs`

## Mermaid Diagram

Evaluation and metrics flow:

- `docs/superpowers/diagrams/evaluation-and-metrics-flow.mmd`

## API Contract

### Eval Datasets

`POST /api/projects/{project_id}/eval/datasets`

Creates a project-scoped eval dataset.

Example request:

```json
{
  "name": "Support Handbook Eval",
  "description": "Core support policy questions"
}
```

`GET /api/projects/{project_id}/eval/datasets`

Lists eval datasets for one project.

`DELETE /api/projects/{project_id}/eval/datasets/{dataset_id}`

Deletes one dataset and its owned questions, runs, and results.

### Eval Questions

`POST /api/projects/{project_id}/eval/datasets/{dataset_id}/questions`

Adds one test question.

Example request:

```json
{
  "question": "When should support escalate an issue?",
  "expected_document_id": null,
  "expected_chunk_id": null,
  "expected_answer_notes": "Should mention severity and SLA breach.",
  "should_answer": true
}
```

`GET /api/projects/{project_id}/eval/datasets/{dataset_id}/questions`

Lists questions for one dataset.

`DELETE /api/projects/{project_id}/eval/datasets/{dataset_id}/questions/{question_id}`

Deletes one question.

### Eval Runs

`POST /api/projects/{project_id}/eval/datasets/{dataset_id}/runs`

Runs one dataset with selected retrieval settings.

Example request:

```json
{
  "retrieval_mode": "hybrid",
  "top_k": 8,
  "vector_weight": 0.65,
  "keyword_weight": 0.35,
  "reranker_enabled": false,
  "reranker_candidate_limit": 40,
  "judge_enabled": false
}
```

`GET /api/projects/{project_id}/eval/datasets/{dataset_id}/runs`

Lists run history for one dataset.

`GET /api/projects/{project_id}/eval/datasets/{dataset_id}/runs/{run_id}`

Fetches one run with per-question results.

### Chat Metrics

`GET /api/projects/{project_id}/metrics/chat`

Returns aggregate chat request metrics and recent chat request rows.

Current response shape:

```json
{
  "summary": {
    "request_count": 12,
    "avg_latency_ms": 1800,
    "avg_retrieval_latency_ms": 140,
    "avg_generation_latency_ms": 1600,
    "avg_citation_count": 3
  },
  "items": []
}
```

## Metric Definitions

### Retrieval Hit Rate

Used when an eval question has `expected_chunk_id` or `expected_document_id`.

```text
hit = expected_chunk_id in retrieved chunks
   or expected_document_id in retrieved documents
```

```text
retrieval_hit_rate = hit_count / answerable_question_count_with_expected_source
```

### Citation Coverage

Used when an answer has citations and the question has an expected source.

```text
citation_covered = expected_chunk_id cited
                or expected_document_id cited
```

```text
citation_coverage = citation_covered_count / answered_question_count_with_expected_source
```

### Refusal Accuracy

Used for questions with `should_answer = false`.

```text
refusal_accuracy = correctly_refused_count / should_not_answer_question_count
```

The current implementation records refusal behavior in eval result metadata and aggregate metrics.

### Answer Match

Used when a question has `expected_answer_notes`.

```text
answer_matched = answer covers expected_answer_notes
```

This is useful for simple local eval sets where expected notes are lightweight rather than full reference answers.

### LLM Judge

When `judge_enabled = true`, an OpenAI-compatible chat provider judges whether the generated answer satisfies the question and expected notes.

Stored judge metadata includes:

- judge enabled flag
- pass/fail result
- score
- reason
- judge model
- judge error if provider execution fails

### Latency

Tracked values:

```text
retrieval_latency_ms
generation_latency_ms
total_latency_ms
```

Current summaries use averages. p50/p95 percentiles can be added later after more metrics rows are accumulated.

### Chat Metrics

The `chat_request_metrics` table stores one row per successful chat request:

- project
- conversation
- retrieval log
- model
- total latency
- retrieval latency
- generation latency
- citation count

## Eval Run Behavior

For each eval question:

1. run project-scoped retrieval with selected options
2. optionally apply the local reranker
3. compute retrieval hit
4. run answer generation through existing chat orchestration
5. compute citation coverage and refusal behavior
6. optionally call the LLM judge
7. store per-question eval result
8. update run-level aggregate metrics

Current execution is synchronous and intended for small local datasets.

## Frontend Behavior

The `/eval` page supports:

- project selection
- dataset creation and deletion through modal actions
- question creation and deletion
- dataset questions tab
- run history tab
- run configuration for retrieval mode, weights, top-k, reranker, and judge
- result filters
- run compare with up to four selected runs
- run export as CSV/JSON
- compare export as CSV

The `/metrics` page supports:

- project selection
- chat metric summary cards
- recent chat request rows
- retrieval log IDs for follow-up inspection

## Project Isolation Rules

Every eval and metrics operation must validate project ownership:

```text
dataset.project_id == project_id
question.project_id == project_id
run.project_id == project_id
result.project_id == project_id
metric.project_id == project_id
```

Do not allow:

- running project A eval dataset against project B
- expected document/chunk from another project
- metrics that aggregate across projects

## Error Contract

Use predictable HTTP statuses:

```text
400 invalid eval run options
400 expected document/chunk does not belong to project
404 project not found
404 dataset not found within selected project
404 question/run not found within selected project
422 invalid payload
500 unexpected eval execution failure
```

If one eval question fails during a run:

- store a failed result for that question when possible
- continue the run when possible
- mark the whole run failed only if orchestration cannot continue

## Verification Commands

Backend:

```bash
cd apps/api
pytest
```

Frontend:

```bash
cd apps/web
pnpm lint
node --experimental-strip-types --test lib/*.test.mjs
```

Manual smoke checks:

```text
POST /api/projects/{project_id}/eval/datasets/{dataset_id}/runs
GET  /api/projects/{project_id}/metrics/chat
```

## Acceptance Criteria

- Eval datasets and questions are project-scoped.
- Eval runs execute retrieval and answer generation for dataset questions.
- Eval runs can compare baseline and reranker settings.
- LLM judge can be enabled per run.
- Per-question eval results are stored.
- Run-level metrics include retrieval hit rate, citation coverage, refusal behavior, answer match, judge match, and latency.
- Eval results can be filtered and exported.
- Multiple runs can be compared in the frontend.
- Chat metrics are stored and exposed through the metrics API and UI.
- Tests prove eval and metrics do not cross project boundaries.

## Future Work

- Async eval execution through RQ for larger datasets.
- Token and cost/request tracking.
- p50/p95 latency metrics.
- Trend charts across time.
- Stronger model-based reranker provider.
- External observability integration if local logs become insufficient.
