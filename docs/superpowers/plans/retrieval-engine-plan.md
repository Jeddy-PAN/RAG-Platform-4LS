# Retrieval Engine Plan

> This is a lightweight module plan. It documents retrieval modes, query boundaries, score contracts, logging, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Implement project-scoped vector, keyword, and hybrid retrieval over indexed chunks, with debug-friendly scoring and retrieval logs.

**Architecture:** The backend exposes a retrieval API used by the Retrieval Playground and later by RAG Chat. The retrieval engine queries only chunks in the selected project, supports vector search through pgvector, keyword search through PostgreSQL full-text search, and hybrid score fusion in application code. Every retrieval call records enough detail to support evaluation and tuning.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, pgvector, PostgreSQL full-text search, OpenAI-compatible embedding provider, pytest.

---

## Scope

This plan covers:

- retrieval request/response contract
- vector retrieval
- keyword retrieval
- hybrid retrieval
- query embedding boundary
- score normalization
- score fusion
- retrieval logs
- project isolation tests
- debug fields for Retrieval Playground

This plan does not cover:

- document parsing
- ingestion
- answer generation
- citations
- reranking implementation
- frontend Retrieval Playground UI
- eval dashboard

## File Changes

Retrieval modules:

- `apps/api/app/rag/retrieval/types.py`
- `apps/api/app/rag/retrieval/vector.py`
- `apps/api/app/rag/retrieval/keyword.py`
- `apps/api/app/rag/retrieval/hybrid.py`
- `apps/api/app/rag/retrieval/service.py`

API and schemas:

- `apps/api/app/api/retrieval.py`
- `apps/api/app/schemas/retrieval.py`
- `apps/api/app/main.py`

Services:

- `apps/api/app/services/retrieval_logs.py`

Tests:

- `apps/api/tests/test_vector_retrieval.py`
- `apps/api/tests/test_keyword_retrieval.py`
- `apps/api/tests/test_hybrid_retrieval.py`
- `apps/api/tests/test_retrieval_api.py`
- `apps/api/tests/test_retrieval_project_isolation.py`
- `apps/api/tests/test_retrieval_logging.py`

## Mermaid Diagram

Retrieval flow diagram:

- `docs/superpowers/diagrams/retrieval-engine-flow.mmd`

## API Contract

`POST /api/projects/{project_id}/retrieval/query`

Purpose:

- run retrieval without answer generation
- power Retrieval Playground
- expose raw and fused scoring details

Request:

```json
{
  "query": "What does the support handbook say about escalation?",
  "mode": "hybrid",
  "top_k": 8,
  "vector_weight": 0.65,
  "keyword_weight": 0.35,
  "similarity_threshold": 0.2
}
```

Response:

```json
{
  "query": "What does the support handbook say about escalation?",
  "mode": "hybrid",
  "top_k": 8,
  "latency_ms": 123,
  "results": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "document_name": "support-handbook.pdf",
      "chunk_index": 12,
      "text_preview": "Escalation should begin when...",
      "source_metadata": {
        "page_number": 4
      },
      "vector_score": 0.82,
      "keyword_score": 0.51,
      "fused_score": 0.71,
      "rank": 1
    }
  ],
  "retrieval_log_id": "uuid"
}
```

Supported modes:

```text
vector
keyword
hybrid
```

Validation:

- `query` must be non-empty
- `top_k` should be bounded, for example `1 <= top_k <= 50`
- `vector_weight` and `keyword_weight` should be between `0` and `1`
- hybrid mode should normalize weights or reject zero-total weights

## Project Isolation Rule

Every retrieval query must include:

```python
where(Chunk.project_id == project_id)
```

This applies to:

- vector retrieval
- keyword retrieval
- hybrid candidate fetching
- retrieval log writes
- retrieval log chunk writes

No retrieval path may query chunks only by `chunk_id` or `document_id` without validating `project_id`.

## Vector Retrieval

Input:

```text
project_id
query
top_k
similarity_threshold
```

Flow:

1. embed query through embedding provider
2. validate embedding dimension
3. query `chunks.embedding` with cosine distance
4. filter by `project_id`
5. filter out missing embeddings
6. convert distance into a score
7. return top candidates

Score convention:

```text
vector_score = higher is better
```

Implementation can use either direct pgvector ordering or a small repository function hiding the SQL details.

## Keyword Retrieval

Input:

```text
project_id
query
top_k
```

Flow:

1. convert query into PostgreSQL text search query
2. search `chunks.search_vector`
3. filter by `project_id`
4. compute rank with PostgreSQL full-text ranking
5. return top candidates

Score convention:

```text
keyword_score = higher is better
```

V1 can use PostgreSQL `simple` dictionary. Chinese-heavy keyword behavior can be revisited after the full RAG loop works.

## Hybrid Retrieval

Hybrid mode combines vector and keyword candidates.

Recommended flow:

1. fetch vector candidates with an expanded limit
2. fetch keyword candidates with an expanded limit
3. merge by `chunk_id`
4. normalize vector scores to `0..1`
5. normalize keyword scores to `0..1`
6. compute fused score
7. sort by fused score
8. return top_k

Suggested formula:

```text
fused_score = vector_weight * normalized_vector_score
            + keyword_weight * normalized_keyword_score
```

Candidate expansion:

```text
candidate_limit = max(top_k * 3, 20)
```

This gives hybrid fusion enough candidates without making v1 overly complex.

## Score Debug Contract

Each returned result should include:

```text
rank
chunk_id
document_id
chunk_index
text_preview
source_metadata
vector_score
keyword_score
fused_score
score_metadata
```

For missing modality scores:

```text
vector-only result in hybrid: keyword_score = null or 0 before normalization
keyword-only result in hybrid: vector_score = null or 0 before normalization
```

Pick one convention during implementation and keep API responses consistent. Preferred v1:

```text
raw missing score = null
normalized missing score = 0
```

## Retrieval Logs

Every retrieval API call should create:

`retrieval_logs`

- `project_id`
- `query`
- `mode`
- `top_k`
- `latency_ms`
- `retrieval_metadata`

`retrieval_log_chunks`

- `project_id`
- `retrieval_log_id`
- `chunk_id`
- `rank`
- `vector_score`
- `keyword_score`
- `fused_score`
- `score_metadata`

Purpose:

- support Retrieval Playground debugging
- support later eval metrics
- support answer-generation traceability

## Error Contract

Use predictable HTTP statuses:

```text
400 invalid retrieval mode
400 empty query
400 invalid top_k or weights
404 project not found
503 embedding provider unavailable
500 unexpected retrieval/database failure
```

Embedding provider failures should be visible as retrieval failures in vector and hybrid modes. Keyword-only mode should not require an embedding call.

## Reranker Extension Point

Reranking is out of scope for this plan, but the return contract should allow a later reranker step.

Future fields:

```text
rerank_score
rerank_model
rerank_metadata
```

Do not add reranking implementation in v1 retrieval engine unless the spec is revised.

## Implementation Sequence

1. Add retrieval schema types.
2. Add retrieval result domain types.
3. Add vector retrieval function.
4. Add keyword retrieval function.
5. Add score normalization helper.
6. Add hybrid merge/fusion function.
7. Add retrieval log service.
8. Add retrieval API route.
9. Register route in FastAPI app.
10. Add vector retrieval tests.
11. Add keyword retrieval tests.
12. Add hybrid fusion tests.
13. Add retrieval API validation tests.
14. Add project isolation tests.
15. Add retrieval logging tests.

## Test Plan

### Vector Retrieval Tests

Verify:

- query embedding is requested once per vector retrieval call
- chunks are filtered by `project_id`
- missing embeddings are ignored
- higher vector score ranks earlier
- similarity threshold filters weak results

### Keyword Retrieval Tests

Verify:

- keyword retrieval does not call embedding provider
- chunks are filtered by `project_id`
- matching chunks rank above non-matching chunks
- empty query is rejected before database search

### Hybrid Retrieval Tests

Verify:

- vector and keyword candidates are merged by `chunk_id`
- scores are normalized before fusion
- fused score respects configured weights
- vector-only and keyword-only candidates are handled consistently
- final result count does not exceed `top_k`

### API Tests

Verify:

- `vector`, `keyword`, and `hybrid` modes work
- invalid mode returns 400
- invalid weights return 400
- missing project returns 404
- response includes score debug fields
- response includes `retrieval_log_id`

### Logging Tests

Verify:

- each retrieval API call creates one retrieval log
- returned chunks are stored in `retrieval_log_chunks`
- logs are scoped by `project_id`
- latency is recorded

### Project Isolation Tests

Create two projects:

```text
project_a -> chunk: "alpha escalation policy"
project_b -> chunk: "beta escalation policy"
```

Verify:

- retrieval in project A never returns project B chunks
- retrieval in project B never returns project A chunks
- this holds for vector, keyword, and hybrid modes

## Verification Commands

Retrieval unit tests:

```bash
cd apps/api
pytest tests/test_vector_retrieval.py tests/test_keyword_retrieval.py tests/test_hybrid_retrieval.py -v
```

API/logging/isolation tests:

```bash
cd apps/api
pytest tests/test_retrieval_api.py tests/test_retrieval_logging.py tests/test_retrieval_project_isolation.py -v
```

Full backend suite:

```bash
cd apps/api
pytest -v
```

Manual smoke test after implementation:

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/retrieval/query \
  -H "Content-Type: application/json" \
  -d '{"query":"escalation policy","mode":"hybrid","top_k":5,"vector_weight":0.65,"keyword_weight":0.35}'
```

Expected:

```text
Response includes results, score fields, and retrieval_log_id.
```

## Acceptance Criteria

- Retrieval API supports vector, keyword, and hybrid modes.
- All retrieval modes are project-scoped.
- Keyword-only retrieval does not require embedding provider access.
- Hybrid retrieval exposes vector, keyword, and fused scores.
- Retrieval logs are written for every retrieval API call.
- Retrieval results include enough debug fields for the future Retrieval Playground.
- Tests prove retrieval does not cross project boundaries.
- No git commit is made.

## Open Design Notes

- Score normalization should remain simple and explainable in v1.
- PostgreSQL full-text search with `simple` dictionary is acceptable initially, but Chinese-heavy search may require later improvements.
- Reranking is a planned extension point, not part of this module.
