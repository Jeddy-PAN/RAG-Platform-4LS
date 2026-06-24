# Local Enterprise RAG Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the confirmed local Enterprise RAG Platform as a maintainable, project-isolated RAG workbench.

**Architecture:** The platform uses a FastAPI backend, Next.js frontend, PostgreSQL with pgvector/full-text search, Redis/RQ background workers, OpenAI-compatible model providers, and Docker Compose. Work is split into module plans so each subsystem can be reviewed, tested, and adjusted without forcing the whole platform into one large implementation pass.

**Tech Stack:** FastAPI, Python, SQLAlchemy or SQLModel, Alembic, PostgreSQL, pgvector, Redis, RQ, Next.js, React, TypeScript, Docker Compose, PyMuPDF, python-docx, openpyxl.

---

## Source Spec

Primary design spec:

- `docs/superpowers/specs/local-enterprise-rag-platform-design.md`

User naming preference:

- Documentation filenames must not include dates.

## Scope Strategy

The overall spec covers multiple subsystems. Implementing it as one plan would be too large to review safely. Use this master plan as the roadmap, then create one implementation-level sub-plan per major subsystem before writing code.

Each sub-plan should:

- use a filename without dates
- include exact files to create or modify
- include test-first steps where practical
- produce runnable software at the end of the plan
- keep the system project-isolated through `project_id`

## Proposed Repository Layout

```text
.
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── ingestion/
│   │   │   ├── models/
│   │   │   ├── rag/
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   ├── workers/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── alembic/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   └── web/
│       ├── app/
│       ├── components/
│       ├── lib/
│       ├── package.json
│       └── Dockerfile
├── docs/
│   └── superpowers/
│       ├── specs/
│       └── plans/
├── docker-compose.yml
├── .env.example
└── README.md
```

## Sub-Plan 1: Project Foundation And Docker Compose

**Output plan file:** `docs/superpowers/plans/foundation-and-compose-plan.md`

**Goal:** Create the repository skeleton, backend shell, frontend shell, PostgreSQL, Redis, worker entrypoint, environment template, and health checks.

**Files:**

- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `README.md`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/Dockerfile`
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/app/api/health.py`
- Create: `apps/api/app/workers/worker.py`
- Create: `apps/api/tests/test_health.py`
- Create: `apps/web/package.json`
- Create: `apps/web/Dockerfile`
- Create: `apps/web/app/page.tsx`

**Required checks:**

- Backend health endpoint returns `{"status":"ok"}`.
- Docker Compose starts `postgres`, `redis`, `backend`, `worker`, and `frontend`.
- `.env.example` contains provider variables but no real secrets.

## Sub-Plan 2: Database Schema And Project Isolation

**Output plan file:** `docs/superpowers/plans/database-and-project-isolation-plan.md`

**Goal:** Add database migrations and models for projects, documents, sections, chunks, conversations, messages, retrieval logs, feedback, eval, and ingestion jobs.

**Files:**

- Create: `apps/api/app/db/session.py`
- Create: `apps/api/app/db/base.py`
- Create: `apps/api/app/models/project.py`
- Create: `apps/api/app/models/document.py`
- Create: `apps/api/app/models/chunk.py`
- Create: `apps/api/app/models/conversation.py`
- Create: `apps/api/app/models/retrieval.py`
- Create: `apps/api/app/models/feedback.py`
- Create: `apps/api/app/models/eval.py`
- Create: `apps/api/alembic/versions/initial_schema.py`
- Create: `apps/api/tests/test_project_isolation_schema.py`

**Required checks:**

- `pgvector` extension is enabled.
- Core tables include `project_id`.
- Retrieval-related queries can be constrained by `project_id`.
- Cross-project test fixtures prove chunks from one project are not returned for another project.

## Sub-Plan 3: Project And Document APIs

**Output plan file:** `docs/superpowers/plans/project-and-document-api-plan.md`

**Goal:** Implement project CRUD, file upload, document records, local file storage, and ingestion job creation.

**Files:**

- Create: `apps/api/app/api/projects.py`
- Create: `apps/api/app/api/documents.py`
- Create: `apps/api/app/schemas/project.py`
- Create: `apps/api/app/schemas/document.py`
- Create: `apps/api/app/services/projects.py`
- Create: `apps/api/app/services/documents.py`
- Create: `apps/api/tests/test_projects_api.py`
- Create: `apps/api/tests/test_documents_api.py`

**Required checks:**

- User can create, list, update, and delete projects.
- User can upload PDF, DOCX, TXT, and XLSX files into a selected project.
- Upload creates a document row and an ingestion job row.
- Unsupported file types are rejected with a clear 400 response.

## Sub-Plan 4: Ingestion Pipeline

**Output plan file:** `docs/superpowers/plans/ingestion-pipeline-plan.md`

**Goal:** Parse uploaded documents, normalize extracted sections, chunk text, generate content hashes, call embedding provider, and store chunks with vector/full-text indexes.

**Files:**

- Create: `apps/api/app/ingestion/parsers/base.py`
- Create: `apps/api/app/ingestion/parsers/pdf.py`
- Create: `apps/api/app/ingestion/parsers/docx.py`
- Create: `apps/api/app/ingestion/parsers/txt.py`
- Create: `apps/api/app/ingestion/parsers/xlsx.py`
- Create: `apps/api/app/ingestion/chunker.py`
- Create: `apps/api/app/ingestion/pipeline.py`
- Create: `apps/api/app/rag/providers/embeddings.py`
- Create: `apps/api/tests/test_parsers.py`
- Create: `apps/api/tests/test_chunker.py`
- Create: `apps/api/tests/test_ingestion_pipeline.py`

**Required checks:**

- Each supported file type produces normalized sections.
- Chunking is deterministic.
- Failed parsing marks the ingestion job as failed.
- Successful ingestion creates chunks with metadata, hash, embedding vector, and full-text search data.
- Embedding dimension mismatches fail before database insertion.

## Sub-Plan 5: Retrieval Engine

**Output plan file:** `docs/superpowers/plans/retrieval-engine-plan.md`

**Goal:** Implement vector search, keyword search, hybrid score fusion, retrieval logs, and project-scoped retrieval APIs.

**Files:**

- Create: `apps/api/app/rag/retrieval/types.py`
- Create: `apps/api/app/rag/retrieval/vector.py`
- Create: `apps/api/app/rag/retrieval/keyword.py`
- Create: `apps/api/app/rag/retrieval/hybrid.py`
- Create: `apps/api/app/api/retrieval.py`
- Create: `apps/api/app/schemas/retrieval.py`
- Create: `apps/api/tests/test_vector_retrieval.py`
- Create: `apps/api/tests/test_keyword_retrieval.py`
- Create: `apps/api/tests/test_hybrid_retrieval.py`
- Create: `apps/api/tests/test_retrieval_project_isolation.py`

**Required checks:**

- Retrieval supports `vector`, `keyword`, and `hybrid` modes.
- Every retrieval query requires `project_id`.
- Hybrid results include vector score, keyword score, and fused score.
- Retrieval logs store query, mode, scores, returned chunks, and latency.

## Sub-Plan 6: Chat, Citations, And Feedback

**Output plan file:** `docs/superpowers/plans/chat-citation-feedback-plan.md`

**Goal:** Implement OpenAI-compatible chat provider, answer generation, citation persistence, conversation history, no-answer behavior, and feedback capture.

**Files:**

- Create: `apps/api/app/rag/providers/chat.py`
- Create: `apps/api/app/rag/prompting.py`
- Create: `apps/api/app/rag/answering.py`
- Create: `apps/api/app/api/chat.py`
- Create: `apps/api/app/api/feedback.py`
- Create: `apps/api/app/schemas/chat.py`
- Create: `apps/api/app/schemas/feedback.py`
- Create: `apps/api/tests/test_chat_provider.py`
- Create: `apps/api/tests/test_answer_generation.py`
- Create: `apps/api/tests/test_citations.py`
- Create: `apps/api/tests/test_feedback_api.py`

**Required checks:**

- Chat runs against one selected project.
- Answers include citation records linked to chunks.
- Weak retrieval context triggers no-answer behavior.
- Feedback can be recorded against assistant messages.

## Sub-Plan 7: Evaluation And Metrics

**Output plan file:** `docs/superpowers/plans/evaluation-and-metrics-plan.md`

**Goal:** Add lightweight eval datasets, eval runs, retrieval hit rate, citation coverage, latency metrics, and dashboard-ready summaries.

**Files:**

- Create: `apps/api/app/api/eval.py`
- Create: `apps/api/app/services/eval.py`
- Create: `apps/api/app/services/metrics.py`
- Create: `apps/api/app/schemas/eval.py`
- Create: `apps/api/tests/test_eval_api.py`
- Create: `apps/api/tests/test_eval_metrics.py`

**Required checks:**

- Eval questions can be created per project.
- Eval runs execute retrieval and answer generation.
- Results include hit rate, citation coverage, refusal behavior, and latency.
- Metrics endpoints are scoped by project.

## Sub-Plan 8: Frontend Workbench

**Output plan file:** `docs/superpowers/plans/frontend-workbench-plan.md`

**Goal:** Build the initial Next.js UI for Dashboard, Projects, Knowledge Base, RAG Chat, and Retrieval Playground.

**Files:**

- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Create: `apps/web/app/projects/page.tsx`
- Create: `apps/web/app/projects/[projectId]/page.tsx`
- Create: `apps/web/app/projects/[projectId]/knowledge/page.tsx`
- Create: `apps/web/app/projects/[projectId]/chat/page.tsx`
- Create: `apps/web/app/projects/[projectId]/retrieval/page.tsx`
- Create: `apps/web/components/app-shell.tsx`
- Create: `apps/web/components/project-switcher.tsx`
- Create: `apps/web/components/document-upload.tsx`
- Create: `apps/web/components/chat-panel.tsx`
- Create: `apps/web/components/citation-list.tsx`
- Create: `apps/web/components/retrieval-results.tsx`
- Create: `apps/web/lib/api.ts`

**Required checks:**

- User can create and open projects.
- User can upload supported documents.
- User can see ingestion status.
- User can chat with citations.
- User can run retrieval-only queries and compare retrieval modes.

## Sub-Plan 9: Documentation And Local Usage

**Output plan file:** `docs/superpowers/plans/documentation-and-local-usage-plan.md`

**Goal:** Document setup, configuration, provider examples, sample workflow, troubleshooting, and current limitations.

**Files:**

- Modify: `README.md`
- Create: `docs/local-setup.md`
- Create: `docs/provider-configuration.md`
- Create: `docs/rag-evaluation-guide.md`
- Create: `docs/sample-workflow.md`

**Required checks:**

- A new user can run the system locally from the docs.
- API keys are configured through `.env`.
- The docs explain project isolation, hybrid retrieval, citations, and eval metrics.

## Execution Order

- [ ] **Step 1: Write and review `foundation-and-compose-plan.md`.**

Run:

```bash
ls docs/superpowers/specs/local-enterprise-rag-platform-design.md
```

Expected: the spec file exists.

- [ ] **Step 2: Execute the foundation plan.**

Expected: backend, frontend, PostgreSQL, Redis, and worker start locally.

- [ ] **Step 3: Write and review `database-and-project-isolation-plan.md`.**

Expected: schema tasks explicitly cover `project_id` isolation tests.

- [ ] **Step 4: Execute the database plan.**

Expected: migrations run and tests prove project isolation.

- [ ] **Step 5: Write and review `project-and-document-api-plan.md`.**

Expected: API tasks cover project CRUD and upload validation.

- [ ] **Step 6: Execute the project and document API plan.**

Expected: projects and documents can be managed through backend APIs.

- [ ] **Step 7: Write and review `ingestion-pipeline-plan.md`.**

Expected: parser, chunker, embedding provider, and ingestion tests are specified.

- [ ] **Step 8: Execute the ingestion plan.**

Expected: PDF, DOCX, TXT, and XLSX files produce indexed chunks.

- [ ] **Step 9: Write and review `retrieval-engine-plan.md`.**

Expected: vector, keyword, and hybrid retrieval are independently testable.

- [ ] **Step 10: Execute the retrieval plan.**

Expected: retrieval API returns project-scoped chunks with debug scores.

- [ ] **Step 11: Write and review `chat-citation-feedback-plan.md`.**

Expected: chat, citations, no-answer behavior, and feedback are covered.

- [ ] **Step 12: Execute the chat plan.**

Expected: answers include persisted citations and feedback can be submitted.

- [ ] **Step 13: Write and review `evaluation-and-metrics-plan.md`.**

Expected: eval datasets, eval runs, and metrics are covered.

- [ ] **Step 14: Execute the evaluation plan.**

Expected: retrieval and answer quality metrics can be computed per project.

- [ ] **Step 15: Write and review `frontend-workbench-plan.md`.**

Expected: pages map to the approved V1 frontend modules only.

- [ ] **Step 16: Execute the frontend plan.**

Expected: Dashboard, Projects, Knowledge Base, RAG Chat, and Retrieval Playground work against the backend.

- [ ] **Step 17: Write and review `documentation-and-local-usage-plan.md`.**

Expected: local setup and RAG usage are documented.

- [ ] **Step 18: Execute the documentation plan.**

Expected: README and docs allow local setup and explain system behavior.

## Global Verification

After all sub-plans are executed, run:

```bash
docker compose up --build
```

Expected:

- frontend starts
- backend starts
- worker starts
- PostgreSQL starts with pgvector
- Redis starts

Run backend tests:

```bash
cd apps/api
pytest
```

Expected:

- all backend tests pass

Run frontend checks:

```bash
cd apps/web
pnpm lint
pnpm build
```

Expected:

- lint passes
- production build succeeds

Manual acceptance workflow:

1. Create two projects.
2. Upload at least one document into each project.
3. Wait for ingestion to finish.
4. Ask a question in project A that only project B can answer.
5. Confirm project A does not retrieve project B chunks.
6. Ask a question in project B.
7. Confirm the answer includes citations.
8. Run Retrieval Playground in vector, keyword, and hybrid modes.
9. Submit useful/not useful feedback.
10. Confirm dashboard metrics update.

## Plan Review Notes

- The overall spec is intentionally split into sub-plans because the platform contains several independent subsystems.
- Do not implement all modules in one pass.
- Do not add multi-user auth, Qdrant, OpenSearch, LangChain, LangGraph, Langfuse, or Kubernetes in V1 unless the spec is revised first.
- Keep file and documentation names stable and date-free.
