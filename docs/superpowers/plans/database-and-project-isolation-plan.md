# Database And Project Isolation Plan

> This is a lightweight module plan. It documents design decisions, schema shape, implementation sequence, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Add the database layer, migrations, core relational schema, pgvector support, full-text search fields, and project isolation guarantees.

**Architecture:** PostgreSQL is the single persistence layer for business data, vectors, and keyword search. `projects` is the isolation root. All project-owned records carry a non-null `project_id`, and all retrieval/chat/eval queries must filter by `project_id`.

**Tech Stack:** SQLAlchemy 2.0, Alembic, PostgreSQL, pgvector, psycopg, pytest.

---

## Scope

This plan covers:

- database dependencies
- SQLAlchemy base/session setup
- Alembic configuration
- initial schema migration
- pgvector extension
- full-text search vector on chunks
- project isolation tests

This plan does not cover:

- project CRUD APIs
- document upload APIs
- ingestion pipeline
- retrieval implementation
- chat generation
- frontend pages

## Design Decisions

- Use SQLAlchemy 2.0 instead of SQLModel.
- Use Alembic for schema migrations.
- Use UUID primary keys for application tables.
- Use timezone-aware `created_at` and `updated_at`.
- Use `project_id` as the core isolation boundary.
- Use `ON DELETE CASCADE` for project-owned child records.
- Store vectors in PostgreSQL through pgvector.
- Store keyword search material in PostgreSQL `tsvector`.
- Keep secrets in `.env`; do not store API keys in `app_settings`.

## File Changes

Backend dependency/config files:

- `apps/api/pyproject.toml`
- `.env.example`

Database infrastructure:

- `apps/api/app/db/base.py`
- `apps/api/app/db/session.py`
- `apps/api/alembic.ini`
- `apps/api/alembic/env.py`
- `apps/api/alembic/versions/initial_schema.py`

Model modules:

- `apps/api/app/models/base.py`
- `apps/api/app/models/project.py`
- `apps/api/app/models/document.py`
- `apps/api/app/models/chunk.py`
- `apps/api/app/models/conversation.py`
- `apps/api/app/models/retrieval.py`
- `apps/api/app/models/feedback.py`
- `apps/api/app/models/eval.py`
- `apps/api/app/models/settings.py`

Tests:

- `apps/api/tests/test_model_metadata.py`
- `apps/api/tests/test_project_isolation_schema.py`
- `apps/api/tests/test_alembic_migration.py`

## Schema Outline

Data model diagram:

- `docs/superpowers/diagrams/project-isolation-data-model.mmd`

### Global Tables

`projects`

- `id`
- `name`
- `description`
- `created_at`
- `updated_at`

`app_settings`

- `id`
- `key`
- `value`
- `description`
- `created_at`
- `updated_at`

Notes:

- `projects` is the root entity.
- `app_settings` is for non-secret runtime preferences only.

### Document Tables

`documents`

- `id`
- `project_id`
- `filename`
- `content_type`
- `storage_path`
- `file_size_bytes`
- `status`
- `error_message`
- `source_metadata`
- `created_at`
- `updated_at`

`document_sections`

- `id`
- `project_id`
- `document_id`
- `section_index`
- `text`
- `source_metadata`
- `created_at`
- `updated_at`

`ingestion_jobs`

- `id`
- `project_id`
- `document_id`
- `status`
- `error_message`
- `job_metadata`
- `created_at`
- `updated_at`

Statuses:

```text
document.status = uploaded | processing | indexed | failed
ingestion_job.status = queued | running | completed | failed
```

### Chunk Table

`chunks`

- `id`
- `project_id`
- `document_id`
- `section_id`
- `chunk_index`
- `text`
- `token_count`
- `content_hash`
- `source_metadata`
- `embedding`
- `search_vector`
- `created_at`
- `updated_at`

Indexes:

- `(project_id, document_id)`
- `(project_id, chunk_index)`
- `content_hash`
- `search_vector` GIN index
- vector index on `embedding`

Important note:

- The initial vector dimension should match the configured embedding provider.
- If the embedding model dimension changes, add a migration instead of silently changing the column.

### Conversation Tables

`conversations`

- `id`
- `project_id`
- `title`
- `created_at`
- `updated_at`

`messages`

- `id`
- `project_id`
- `conversation_id`
- `role`
- `content`
- `message_metadata`
- `created_at`
- `updated_at`

`message_citations`

- `id`
- `project_id`
- `message_id`
- `chunk_id`
- `citation_index`
- `quote`
- `citation_metadata`
- `created_at`
- `updated_at`

Roles:

```text
message.role = user | assistant | system
```

### Retrieval And Feedback Tables

`retrieval_logs`

- `id`
- `project_id`
- `query`
- `mode`
- `top_k`
- `latency_ms`
- `retrieval_metadata`
- `created_at`
- `updated_at`

`retrieval_log_chunks`

- `id`
- `project_id`
- `retrieval_log_id`
- `chunk_id`
- `rank`
- `vector_score`
- `keyword_score`
- `fused_score`
- `score_metadata`
- `created_at`
- `updated_at`

`feedback`

- `id`
- `project_id`
- `conversation_id`
- `message_id`
- `rating`
- `comment`
- `created_at`
- `updated_at`

Enums:

```text
retrieval.mode = vector | keyword | hybrid
feedback.rating = useful | not_useful
```

### Eval Tables

`eval_datasets`

- `id`
- `project_id`
- `name`
- `description`
- `created_at`
- `updated_at`

`eval_questions`

- `id`
- `project_id`
- `dataset_id`
- `question`
- `expected_document_id`
- `expected_chunk_id`
- `expected_answer_notes`
- `should_answer`
- `created_at`
- `updated_at`

`eval_runs`

- `id`
- `project_id`
- `dataset_id`
- `status`
- `retrieval_mode`
- `top_k`
- `metrics`
- `error_message`
- `created_at`
- `updated_at`

`eval_results`

- `id`
- `project_id`
- `run_id`
- `question_id`
- `answer`
- `hit`
- `citation_covered`
- `refused`
- `retrieval_latency_ms`
- `generation_latency_ms`
- `score`
- `result_metadata`
- `created_at`
- `updated_at`

## Project Isolation Rule

Every project-owned table must include:

```text
project_id NOT NULL REFERENCES projects(id) ON DELETE CASCADE
```

Project-owned tables:

- `documents`
- `document_sections`
- `ingestion_jobs`
- `chunks`
- `conversations`
- `messages`
- `message_citations`
- `retrieval_logs`
- `retrieval_log_chunks`
- `feedback`
- `eval_datasets`
- `eval_questions`
- `eval_runs`
- `eval_results`

Every retrieval/chat/eval query must include:

```python
where(Model.project_id == selected_project_id)
```

This is not optional. It is the main guard against cross-project knowledge leakage.

## Migration Strategy

Initial migration should:

1. Enable `vector` extension.
2. Create enum types.
3. Create global tables.
4. Create project-owned tables.
5. Create foreign keys.
6. Create indexes.
7. Create chunk full-text search trigger.

Full-text trigger behavior:

```sql
NEW.search_vector = to_tsvector('simple', coalesce(NEW.text, ''))
```

Use the `simple` dictionary in v1 to avoid language-specific assumptions. Chinese tokenization can be revisited after basic retrieval works.

## Implementation Sequence

1. Add database dependencies to `apps/api/pyproject.toml`.
2. Add `TEST_DATABASE_URL` to `.env.example`.
3. Create SQLAlchemy `Base`.
4. Create database engine/session helpers.
5. Create shared UUID/timestamp mixins.
6. Create model modules.
7. Configure Alembic.
8. Write initial migration.
9. Run migration against local PostgreSQL.
10. Add metadata tests.
11. Add migration integration tests.
12. Add project isolation tests.

## Test Plan

### Metadata Tests

Verify:

- all expected tables are registered in SQLAlchemy metadata
- every project-owned table has non-null `project_id`
- `chunks` has `embedding`
- `chunks` has `search_vector`

Example assertion shape:

```python
for table in project_owned_tables:
    assert "project_id" in table.columns
```

### Migration Tests

Verify:

- `vector` extension exists
- all expected tables exist
- `chunks.search_vector` is populated after inserting chunk text
- initial migration can downgrade and upgrade cleanly

### Project Isolation Tests

Create two projects:

```text
project_a -> chunk: "alpha only knowledge"
project_b -> chunk: "beta only knowledge"
```

Verify:

- querying chunks with `project_a.id` returns only project A chunks
- querying chunks with `project_b.id` returns only project B chunks
- an intentionally unscoped query would return both, proving why scoped queries are required

## Verification Commands

Install dependencies:

```bash
cd apps/api
python -m pip install -e ".[dev]"
```

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Run migration:

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag alembic upgrade head
```

Run tests:

```bash
cd apps/api
TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag pytest -v
```

Verify downgrade/upgrade:

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag alembic downgrade base
DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag alembic upgrade head
```

## Acceptance Criteria

- SQLAlchemy database infrastructure exists.
- Alembic can run the initial migration.
- `pgvector` extension is enabled.
- All v1 schema tables exist.
- Project-owned tables have non-null `project_id`.
- Chunk rows support vector retrieval through `embedding`.
- Chunk rows support keyword retrieval through `search_vector`.
- Full-text vector is populated automatically from chunk text.
- Tests prove project-scoped queries do not mix knowledge bases.
- No git commit is made.

## Open Design Notes

- Embedding dimension is fixed by migration. Confirm the first embedding provider before implementation.
- PostgreSQL `simple` full-text search is acceptable for v1, but Chinese-heavy retrieval may need a later keyword-search strategy.
- `app_settings` is included for future non-secret preferences, but provider secrets stay in environment variables.
