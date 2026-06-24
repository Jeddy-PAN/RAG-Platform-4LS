# Evaluation And Metrics Plan

> This is a lightweight module plan. It documents eval data structures, run flow, metric definitions, logging boundaries, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Add lightweight project-scoped RAG evaluation and metrics so retrieval quality, citation behavior, refusal behavior, latency, and feedback trends can be measured locally.

**Architecture:** Evaluation is built on top of existing retrieval and chat orchestration. Users define eval datasets with questions and expected sources, then run evaluations against a project using selected retrieval options. Results are stored per question and summarized per run. Metrics APIs expose dashboard-ready project statistics from retrieval logs, chat records, feedback, and eval results.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, existing retrieval engine, existing chat orchestration, pytest.

---

## Scope

This plan covers:

- eval dataset API
- eval question API
- eval run API
- eval result persistence
- retrieval hit rate
- citation coverage
- refusal behavior
- latency metrics
- feedback useful rate
- project metrics summary API
- dashboard-ready response contracts

This plan does not cover:

- LLM judge implementation
- external observability tools
- Langfuse/Phoenix integration
- frontend dashboard UI
- automated scheduled evals
- advanced statistical analysis

## File Changes

API and schemas:

- `apps/api/app/api/eval.py`
- `apps/api/app/api/metrics.py`
- `apps/api/app/schemas/eval.py`
- `apps/api/app/schemas/metrics.py`
- `apps/api/app/main.py`

Services:

- `apps/api/app/services/eval_datasets.py`
- `apps/api/app/services/eval_runs.py`
- `apps/api/app/services/eval_metrics.py`
- `apps/api/app/services/project_metrics.py`

Tests:

- `apps/api/tests/test_eval_dataset_api.py`
- `apps/api/tests/test_eval_run_api.py`
- `apps/api/tests/test_eval_metrics.py`
- `apps/api/tests/test_project_metrics.py`
- `apps/api/tests/test_eval_project_isolation.py`

## Mermaid Diagram

Evaluation flow diagram:

- `docs/superpowers/diagrams/evaluation-and-metrics-flow.mmd`

## API Contract

### Eval Datasets

`POST /api/projects/{project_id}/eval/datasets`

Purpose:

- create a project-scoped eval dataset

Request:

```json
{
  "name": "Support Handbook Eval",
  "description": "Core support policy questions"
}
```

`GET /api/projects/{project_id}/eval/datasets`

Purpose:

- list eval datasets for one project

`GET /api/projects/{project_id}/eval/datasets/{dataset_id}`

Purpose:

- fetch dataset details and questions

`DELETE /api/projects/{project_id}/eval/datasets/{dataset_id}`

Purpose:

- delete dataset, questions, runs, and results in one project

### Eval Questions

`POST /api/projects/{project_id}/eval/datasets/{dataset_id}/questions`

Purpose:

- add a test question to a dataset

Request:

```json
{
  "question": "When should support escalate an issue?",
  "expected_document_id": "uuid-or-null",
  "expected_chunk_id": "uuid-or-null",
  "expected_answer_notes": "Should mention severity and SLA breach.",
  "should_answer": true
}
```

### Eval Runs

`POST /api/projects/{project_id}/eval/runs`

Purpose:

- execute an eval dataset against selected retrieval/chat settings

Request:

```json
{
  "dataset_id": "uuid",
  "retrieval_mode": "hybrid",
  "top_k": 8,
  "vector_weight": 0.65,
  "keyword_weight": 0.35,
  "run_generation": true
}
```

Response:

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "dataset_id": "uuid",
  "status": "completed",
  "metrics": {
    "question_count": 20,
    "retrieval_hit_rate": 0.75,
    "citation_coverage": 0.7,
    "refusal_accuracy": 0.8,
    "average_retrieval_latency_ms": 120,
    "average_generation_latency_ms": 1800
  }
}
```

`GET /api/projects/{project_id}/eval/runs`

Purpose:

- list eval runs for one project

`GET /api/projects/{project_id}/eval/runs/{run_id}`

Purpose:

- fetch run summary and per-question results

### Project Metrics

`GET /api/projects/{project_id}/metrics/summary`

Purpose:

- return dashboard-ready project metrics

Response shape:

```json
{
  "document_count": 12,
  "chunk_count": 824,
  "conversation_count": 18,
  "query_count": 96,
  "average_retrieval_latency_ms": 130,
  "average_generation_latency_ms": 1900,
  "feedback_useful_rate": 0.72,
  "latest_eval": {
    "run_id": "uuid",
    "retrieval_hit_rate": 0.75,
    "citation_coverage": 0.7,
    "refusal_accuracy": 0.8
  }
}
```

## Metric Definitions

### Retrieval Hit Rate

Used when eval question has `expected_chunk_id` or `expected_document_id`.

```text
hit = expected_chunk_id in retrieved chunks
   or expected_document_id in retrieved documents
```

```text
retrieval_hit_rate = hit_count / answerable_question_count_with_expected_source
```

### Citation Coverage

Used when answer generation runs.

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

V1 refusal detection can be explicit from chat orchestration metadata:

```text
answer_metadata.refused = true | false
```

Do not rely only on string matching if the chat service can provide structured metadata.

### Latency Metrics

Track:

```text
retrieval_latency_ms
generation_latency_ms
total_latency_ms
```

Summaries:

```text
average
p50 optional later
p95 optional later
```

V1 can start with averages.

### Feedback Useful Rate

```text
feedback_useful_rate = useful_feedback_count / total_feedback_count
```

If there is no feedback:

```text
feedback_useful_rate = null
```

## Eval Run Behavior

For each eval question:

1. run retrieval with selected options
2. compute retrieval hit
3. if `run_generation = true`, run chat/answer generation
4. compute citation coverage
5. compute refusal behavior
6. store per-question eval result
7. update run-level aggregate metrics

V1 execution can be synchronous for small datasets.

Reasonable v1 bound:

```text
max questions per run = 100
```

Larger async eval runs can be added later through RQ.

## Project Isolation Rules

Every eval and metrics operation must validate:

```python
dataset.project_id == project_id
question.project_id == project_id
run.project_id == project_id
result.project_id == project_id
```

Metrics queries must filter by:

```python
Model.project_id == project_id
```

Do not allow:

- running project A eval dataset against project B
- expected document/chunk from another project
- dashboard metrics that aggregate across projects

## Error Contract

Use predictable HTTP statuses:

```text
400 invalid eval run options
400 expected document/chunk does not belong to project
404 project not found
404 dataset not found within selected project
404 run not found within selected project
422 invalid question payload
500 unexpected eval execution failure
```

If one eval question fails during a run:

- store a failed result for that question
- continue the run when possible
- mark the whole run failed only if orchestration cannot continue

## Implementation Sequence

1. Add eval schemas.
2. Add metrics schemas.
3. Add eval dataset service.
4. Add eval question service.
5. Add eval metric helper functions.
6. Add eval run orchestration service.
7. Add project metrics summary service.
8. Add eval API routes.
9. Add metrics API route.
10. Register routes in FastAPI app.
11. Add eval dataset API tests.
12. Add eval run API tests.
13. Add metric calculation tests.
14. Add project metrics tests.
15. Add project isolation tests.

## Test Plan

### Eval Dataset Tests

Verify:

- create dataset
- list datasets by project
- add questions
- reject expected document from another project
- reject expected chunk from another project
- delete dataset within selected project

### Eval Run Tests

Verify:

- run retrieval-only eval
- run retrieval + generation eval
- per-question results are stored
- run aggregate metrics are stored
- failed question can be recorded without losing other results
- run cannot use dataset from another project

### Metric Tests

Verify:

- retrieval hit rate with expected chunk
- retrieval hit rate with expected document
- citation coverage with cited chunk
- refusal accuracy for `should_answer = false`
- average latency calculations
- useful feedback rate with no feedback returns null

### Project Metrics Tests

Verify:

- document count is project-scoped
- chunk count is project-scoped
- query count is project-scoped
- average retrieval latency is project-scoped
- latest eval summary is project-scoped

## Verification Commands

Eval tests:

```bash
cd apps/api
pytest tests/test_eval_dataset_api.py tests/test_eval_run_api.py tests/test_eval_metrics.py -v
```

Metrics/isolation tests:

```bash
cd apps/api
pytest tests/test_project_metrics.py tests/test_eval_project_isolation.py -v
```

Full backend suite:

```bash
cd apps/api
pytest -v
```

Manual smoke test after implementation:

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/eval/runs \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"dataset-uuid","retrieval_mode":"hybrid","top_k":5,"run_generation":true}'
```

Expected:

```text
Response includes completed run status and aggregate metrics.
```

## Acceptance Criteria

- Eval datasets and questions are project-scoped.
- Eval runs execute retrieval for dataset questions.
- Eval runs can optionally execute answer generation.
- Per-question eval results are stored.
- Run-level metrics include retrieval hit rate, citation coverage, refusal accuracy, and latency.
- Project metrics summary returns dashboard-ready values.
- Tests prove eval and metrics do not cross project boundaries.
- No git commit is made.

## Open Design Notes

- LLM judge is intentionally out of scope for v1; source-based metrics are more transparent at this stage.
- Synchronous eval execution is acceptable for small local datasets.
- More advanced metrics such as p95 latency, cost/request, and reranker A/B comparison can be added after the base eval loop works.
