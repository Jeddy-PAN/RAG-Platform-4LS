# Foundation And Compose Plan

> This is a lightweight module plan. It documents structure, service boundaries, verification goals, and implementation sequence. Full source code should be generated during implementation, not embedded here.

**Goal:** Create the initial runnable project foundation for the local Enterprise RAG Platform.

**Architecture:** The first milestone creates a monorepo skeleton with a FastAPI backend, Next.js frontend, Redis/RQ worker, PostgreSQL with pgvector image, and Docker Compose orchestration. It does not implement RAG features yet; it proves that the runtime shape is sound.

**Tech Stack:** FastAPI, Python, pytest, Redis, RQ, PostgreSQL pgvector image, Next.js, React, TypeScript, Docker Compose.

---

## Scope

This plan covers:

- repository skeleton
- backend app shell
- backend health endpoint
- frontend app shell
- worker entrypoint
- Dockerfiles
- Docker Compose services
- environment template
- README setup notes

This plan does not cover:

- database schema
- migrations
- project CRUD
- document upload
- RAG pipeline
- retrieval
- chat
- evaluation

## File Changes

Root:

- `.env.example`
- `.gitignore`
- `README.md`
- `docker-compose.yml`

Backend:

- `apps/api/pyproject.toml`
- `apps/api/Dockerfile`
- `apps/api/.dockerignore`
- `apps/api/app/main.py`
- `apps/api/app/core/config.py`
- `apps/api/app/api/health.py`
- `apps/api/app/workers/worker.py`
- `apps/api/tests/test_health.py`

Frontend:

- `apps/web/package.json`
- `apps/web/Dockerfile`
- `apps/web/.dockerignore`
- `apps/web/next.config.ts`
- `apps/web/tsconfig.json`
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/globals.css`

## Runtime Services

`frontend`

- Next.js app
- local port: `3000`
- talks to backend through `NEXT_PUBLIC_API_BASE_URL`

`backend`

- FastAPI app
- local port: `8000`
- exposes `/health`
- later owns API routes, provider config, retrieval orchestration, chat, and eval

`worker`

- Python RQ worker
- connects to Redis
- later runs ingestion jobs

`postgres`

- image: `pgvector/pgvector:pg16`
- local port: `5432`
- later stores relational data, vectors, and full-text search data

`redis`

- image: `redis:7-alpine`
- local port: `6379`
- stores RQ queues and job metadata

## Environment Contract

`.env.example` should include:

```text
APP_NAME
ENVIRONMENT
API_HOST
API_PORT
FRONTEND_PORT
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
DATABASE_URL
REDIS_URL
RQ_QUEUE_NAME
LLM_PROVIDER
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
EMBEDDING_PROVIDER
EMBEDDING_BASE_URL
EMBEDDING_API_KEY
EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
```

Rules:

- `.env.example` contains placeholders only.
- `.env` is ignored by git.
- Real API keys must not be committed.

## Backend Shape

Backend app factory:

```python
create_app() -> FastAPI
```

Initial route:

```text
GET /health -> {"status": "ok"}
```

Configuration:

```python
Settings reads from .env and environment variables.
```

Worker shape:

```python
create_worker() -> RQ Worker connected to configured Redis queue
```

## Frontend Shape

Initial page should communicate the actual product direction:

- local RAG workbench
- project-isolated knowledge bases
- document ingestion
- hybrid retrieval
- cited answers
- evaluation logs

The initial UI can be simple. It should avoid implying features are already implemented.

## Docker Compose Shape

Compose should define:

```text
postgres
redis
backend
worker
frontend
```

Dependency order:

```text
backend depends on postgres + redis
worker depends on postgres + redis
frontend depends on backend
```

Health checks:

- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`

## Implementation Sequence

1. Add root environment and ignore files.
2. Add backend package skeleton.
3. Add FastAPI app factory.
4. Add `/health` endpoint.
5. Add backend health test.
6. Add RQ worker entrypoint.
7. Add backend Dockerfile.
8. Add Next.js app skeleton.
9. Add frontend Dockerfile.
10. Add Docker Compose services.
11. Add README setup instructions.
12. Run local and Compose verification.

## Test Plan

Backend tests:

- health endpoint returns `{"status": "ok"}`
- app factory can be imported

Worker checks:

- worker module imports
- worker can connect to Redis when Compose is running

Frontend checks:

- dependencies install
- production build succeeds
- home page serves through local port `3000`

Compose checks:

- all five services start
- backend health endpoint responds
- Redis responds with `PONG`
- PostgreSQL accepts connections

## Verification Commands

Backend:

```bash
cd apps/api
python -m pip install -e ".[dev]"
pytest
```

Frontend:

```bash
cd apps/web
pnpm install
pnpm build
```

Compose:

```bash
cp .env.example .env
docker compose up --build
```

Runtime checks:

```bash
curl http://localhost:8000/health
curl -I http://localhost:3000
docker compose exec redis redis-cli ping
docker compose exec postgres pg_isready -U rag -d rag
```

## Acceptance Criteria

- `.env.example` exists and contains no real secrets.
- `.gitignore` excludes `.env`, Python caches, Node build output, and local data.
- FastAPI app starts.
- `/health` returns `{"status":"ok"}`.
- Backend tests pass.
- RQ worker entrypoint exists.
- Next.js app builds.
- Docker Compose starts frontend, backend, worker, PostgreSQL, and Redis.
- README explains local startup.
- No git commit is made.

## Open Design Notes

- Keep the initial frontend small; detailed product UI belongs in the frontend workbench plan.
- Keep the worker minimal; ingestion job behavior belongs in the ingestion pipeline plan.
- Keep PostgreSQL migration work out of this plan; schema belongs in the database plan.
