# Local Enterprise RAG Platform

A local, project-isolated RAG workbench for document ingestion, hybrid retrieval, cited answer generation, and lightweight RAG inspection.

## Current Stage

The platform currently includes:

- FastAPI backend with project, document, retrieval, chat, citation, and feedback APIs
- PostgreSQL with pgvector and PostgreSQL full-text search
- Redis + RQ worker for document ingestion
- PDF, DOCX, TXT, and XLSX parsing
- OpenAI-compatible chat and embedding provider boundaries
- Next.js frontend workbench with project/file sidebar, upload zone, chat, citations, feedback, and Retrieval Playground
- Docker Compose local runtime with automatic Alembic migration

## Local Setup

Create a local environment file:

```bash
cp .env.example .env
```

Edit `.env` before using chat or ingestion with real embeddings:

```bash
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-chat-provider-key
LLM_MODEL=deepseek-chat

EMBEDDING_BASE_URL=https://your-embedding-provider.example/v1
EMBEDDING_API_KEY=your-embedding-provider-key
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSIONS=1024
```

The embedding dimension must match the database vector dimension created by the initial migration. The current default is `1024`.

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

Frontend:

```bash
open http://localhost:3000
```

Retrieval Playground:

```bash
open http://localhost:3000/retrieval
```

## Basic Workflow

1. Open the frontend.
2. Create a project with the `+` button.
3. Upload a PDF, DOCX, TXT, or XLSX file into the selected project.
4. Wait for the file status to move from `uploaded` or `processing` to `indexed`.
5. Ask a question in the chat area.
6. Review citations under the assistant answer.
7. Use Retrieval Playground to inspect ranked chunks and retrieval scores.

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
- Do not commit `.env` or real API keys.
