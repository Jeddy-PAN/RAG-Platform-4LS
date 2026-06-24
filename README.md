# Local Enterprise RAG Platform

A local, project-isolated RAG workbench for document ingestion, hybrid retrieval, cited answer generation, and RAG evaluation.

## Current Stage

This repository is being built in planned stages. The first stage provides:

- FastAPI backend shell
- Next.js frontend shell
- PostgreSQL with pgvector image
- Redis
- RQ worker entrypoint
- Docker Compose local runtime
- Health checks

## Local Setup

Create a local environment file:

```bash
cp .env.example .env
```

Start the stack:

```bash
docker compose up --build
```

Backend health:

```bash
curl http://localhost:8000/health
```

Frontend:

```bash
open http://localhost:3000
```

## Development Checks

Backend tests:

```bash
cd apps/api
python -m pip install -e ".[dev]"
pytest
```

Frontend build:

```bash
cd apps/web
pnpm install
pnpm build
```

## Secrets

Do not commit `.env` or real API keys. Use `.env.example` as the template.
