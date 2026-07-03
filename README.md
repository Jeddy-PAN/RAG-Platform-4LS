# Local Enterprise RAG Platform

A local, project-isolated RAG workbench for document ingestion, hybrid retrieval, cited answer generation, evaluation, and lightweight observability.

The project is designed as a small production-style local tool: each project is an isolated knowledge base, documents are parsed and indexed asynchronously, and the UI exposes chat, retrieval inspection, eval runs, and chat metrics.

## Current Capabilities

- FastAPI backend with project, document, ingestion, retrieval, chat, citation, feedback, eval, and metrics APIs
- PostgreSQL with pgvector and PostgreSQL full-text search
- Redis + RQ worker for asynchronous document ingestion
- PDF, DOCX, TXT, and XLSX parsing
- Local-first embedding through Ollama `bge-m3`, with OpenAI-compatible cloud embedding fallback
- OpenAI-compatible cloud chat provider for DeepSeek or similar API-key based providers
- Hybrid retrieval with vector, keyword, and fused scoring
- Lightweight reranker option for retrieval, chat, and eval experiments
- Chat answers with source citations and feedback controls
- Retrieval Playground for inspecting chunks, scores, logs, and reranker effects
- Eval datasets, questions, synchronous runs, LLM judge option, run filtering, run compare, and CSV/JSON export
- Chat metrics dashboard with latency, citation count, recent requests, and linked retrieval logs
- Next.js frontend routes for the workbench, retrieval, eval, and metrics
- Docker Compose local runtime with Alembic migrations

## Local Setup

Create a local environment file:

```bash
cp .env.example .env
```

Install Ollama on macOS and pull the default local embedding model:

```bash
ollama pull bge-m3
```

Edit `.env` before using chat:

```bash
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-chat-provider-key
LLM_MODEL=deepseek-chat
```

The default embedding setup is local Ollama with `bge-m3`:

```bash
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSIONS=1024
```

Use `http://localhost:11434` instead when running the backend directly on macOS instead of through Docker Compose.

If local embedding quality or speed is not good enough, switch to all-cloud by changing only the embedding section:

```bash
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://your-embedding-provider.example/v1
EMBEDDING_API_KEY=your-embedding-provider-key
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSIONS=1024
```

The embedding dimension must match the database vector dimension created by the initial migration. The current default is `1024`, which matches `bge-m3`.

## Run The Stack

Start everything:

```bash
docker compose up --build
```

Docker Compose starts:

- Postgres on `localhost:5433`
- Redis on `localhost:6379`
- Backend on `localhost:8000`
- Frontend on `localhost:3000`
- Worker for ingestion jobs
- One-shot migration service before backend and worker start

Backend health:

```bash
curl http://localhost:8000/health
```

Main frontend routes:

```text
http://localhost:3000
http://localhost:3000/retrieval
http://localhost:3000/eval
http://localhost:3000/metrics
```

## Basic Workflow

1. Open the frontend.
2. Create a project with the `+` button.
3. Select the active project.
4. Upload a PDF, DOCX, TXT, or XLSX file into the selected project.
5. Wait for the file status to move from `uploaded` or `processing` to `indexed`.
6. Ask a question in the chat area.
7. Review citations under the assistant answer.
8. Use feedback controls to mark answer quality.

## Retrieval Workflow

Use `/retrieval` to inspect retrieval behavior before or after chat:

- choose a project
- enter a natural-language query
- select vector, keyword, or hybrid retrieval
- tune `top_k`, vector weight, keyword weight, and reranker settings
- inspect returned chunks, raw scores, fused scores, reranker scores, and retrieval logs

## Evaluation Workflow

Use `/eval` to create project-scoped test datasets:

- create a dataset for one project
- add questions with optional expected document, expected chunk, answer notes, and `should_answer`
- run eval with retrieval settings, optional reranker, and optional LLM judge
- inspect question results, failures, refusal behavior, citation coverage, and answer matching
- compare multiple runs to evaluate retrieval/reranker changes
- export run data as CSV or JSON

## Metrics Workflow

Use `/metrics` to inspect chat request behavior for a project:

- request count
- average total latency
- average retrieval latency
- average generation latency
- average citation count
- recent chat requests linked to retrieval logs

The current metrics API is:

```text
GET /api/projects/{project_id}/metrics/chat
```

## Development Checks

Backend tests:

```bash
cd apps/api
python -m pip install -e ".[dev]"
pytest
```

Frontend checks:

```bash
cd apps/web
pnpm install
pnpm lint
pnpm build
```

Docker Compose config check:

```bash
docker compose config
```

## Environment Notes

- `POSTGRES_HOST_PORT=5433` avoids conflicts with another local Postgres on `5432`.
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` is used by the browser frontend.
- `CORS_ALLOW_ORIGINS` should include the frontend origin.
- `EMBEDDING_PROVIDER=ollama` is the preferred local-first setup.
- `LLM_PROVIDER=openai_compatible` is the preferred cloud chat setup.
- Do not commit `.env` or real API keys.

## Current Limitations

- Eval runs are synchronous and intended for small local datasets.
- Metrics v1 focuses on successful chat requests, latency, citation count, and recent request history.
- Local chat models are intentionally not the primary path yet; the current preferred path is local embedding plus cloud chat.
