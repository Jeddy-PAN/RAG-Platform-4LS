# Documentation And Local Usage Plan

> This is a lightweight module plan. It documents user-facing docs, setup flows, configuration guidance, sample workflows, troubleshooting, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Provide clear local setup and usage documentation so the RAG platform can be installed, configured, run, tested, and used as a long-term local work tool.

**Architecture:** Documentation is split by user intent: quick start, local setup, provider configuration, RAG workflow, evaluation guide, troubleshooting, and architecture references. The README remains concise and links to deeper docs instead of becoming a long manual.

**Tech Stack:** Markdown documentation, Docker Compose, FastAPI backend, Next.js frontend, PostgreSQL/pgvector, Redis/RQ, OpenAI-compatible model providers.

---

## Scope

This plan covers:

- root README structure
- local setup guide
- provider/API key configuration guide
- sample RAG workflow guide
- retrieval/evaluation guide
- troubleshooting guide
- architecture/documentation index

This plan does not cover:

- generated API reference
- public SaaS deployment docs
- Kubernetes docs
- multi-user admin docs
- production cloud hardening docs

## File Changes

Root:

- `README.md`

Documentation:

- `docs/local-setup.md`
- `docs/provider-configuration.md`
- `docs/sample-workflow.md`
- `docs/rag-evaluation-guide.md`
- `docs/troubleshooting.md`
- `docs/architecture.md`

Existing design references:

- `docs/superpowers/specs/local-enterprise-rag-platform-design.md`
- `docs/superpowers/plans/local-enterprise-rag-platform-implementation-plan.md`
- `docs/superpowers/diagrams/`

## README Role

README should be the entry point, not the whole manual.

Recommended sections:

```text
Project overview
Current capabilities
Quick start
Configuration
Common workflows
Documentation map
Development checks
Current limitations
```

README should answer:

- what this project is
- what problem it solves
- how to start it locally
- where to configure model providers
- where to read deeper docs

README should not include:

- real API keys
- huge architecture essays
- full implementation plans
- unsupported future promises

## Local Setup Guide

File:

```text
docs/local-setup.md
```

Should cover:

- prerequisites
- Docker Compose startup
- backend local development
- frontend local development
- worker startup
- database migration
- health checks
- common local ports

Prerequisites:

```text
Docker
Python 3.11+
Node.js / pnpm
```

Local services:

```text
frontend: http://localhost:3000
backend: http://localhost:8000
postgres: localhost:5432
redis: localhost:6379
```

Health checks:

```text
GET /health
redis-cli ping
pg_isready
```

## Provider Configuration Guide

File:

```text
docs/provider-configuration.md
```

Should cover:

- OpenAI-compatible chat provider
- OpenAI-compatible embedding provider
- DeepSeek-style provider example
- OpenRouter/SiliconFlow-style provider example
- local Ollama as optional future path
- embedding dimension warning

Required variables:

```text
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

- never commit `.env`
- never paste real keys into docs
- confirm embedding dimensions before indexing documents
- changing embedding dimensions requires migration/reindex strategy

## Sample Workflow Guide

File:

```text
docs/sample-workflow.md
```

Should document the happy path:

1. Start local services.
2. Create a project.
3. Upload documents.
4. Wait for ingestion.
5. Ask first question.
6. Inspect citations.
7. Submit feedback.
8. Open Retrieval Playground.
9. Compare vector, keyword, and hybrid retrieval.
10. Create a small eval dataset.
11. Run eval.
12. Read metrics.

Example project scenarios:

```text
personal work project
client research folder
product/design docs
internal support knowledge base
```

## RAG Evaluation Guide

File:

```text
docs/rag-evaluation-guide.md
```

Should explain:

- why eval matters
- how to create eval questions
- how expected document/chunk works
- retrieval hit rate
- citation coverage
- refusal accuracy
- latency metrics
- feedback useful rate
- chunk size experiments
- vector vs keyword vs hybrid comparison

Metrics should be explained in practical language:

```text
retrieval_hit_rate: did retrieval find the expected source?
citation_coverage: did the answer cite the expected source?
refusal_accuracy: did the system refuse when it should not answer?
```

Keep this guide focused on learning RAG behavior, not academic benchmarking.

## Troubleshooting Guide

File:

```text
docs/troubleshooting.md
```

Should cover:

- Docker Compose service fails to start
- PostgreSQL connection fails
- Redis connection fails
- migration fails
- pgvector extension missing
- upload fails
- ingestion stuck in queued/running
- parser extracts no text
- embedding provider returns error
- embedding dimension mismatch
- chat provider unavailable
- retrieval returns irrelevant chunks
- citations missing

Each troubleshooting item should include:

```text
symptom
likely cause
how to check
how to fix
```

## Architecture Docs

File:

```text
docs/architecture.md
```

Should summarize:

- runtime services
- project isolation
- ingestion flow
- retrieval flow
- chat/citation flow
- evaluation flow
- where diagrams live

Architecture docs should link to:

- overall spec
- relevant module plans
- Mermaid diagrams

## Documentation Style Rules

Use:

- concise sections
- command blocks with expected result
- explicit file paths
- local-first examples
- no real secrets

Avoid:

- vague "configure as needed"
- huge pasted logs
- unsupported deployment claims
- cloud production promises before they exist
- copying implementation plans into README

## Implementation Sequence

1. Update README as a concise entry point.
2. Add local setup guide.
3. Add provider configuration guide.
4. Add sample workflow guide.
5. Add RAG evaluation guide.
6. Add troubleshooting guide.
7. Add architecture guide.
8. Link docs to existing specs/plans/diagrams.
9. Verify commands and paths are consistent.
10. Run markdown/link sanity checks manually.

## Verification Plan

Manual documentation review:

- README links to deeper docs.
- Setup commands match actual project scripts.
- No real API keys appear in docs.
- Ports match Docker Compose.
- Provider config matches `.env.example`.
- Sample workflow matches frontend/backend capabilities.
- Troubleshooting items are actionable.
- Architecture doc links to diagrams.

Search checks:

```bash
rg -n "sk-|api_key_here|real-api-key|TODO|TBD" README.md docs
```

Expected:

```text
No real secrets and no unfinished placeholders.
```

Path checks:

```bash
find docs -type f | sort
```

Expected:

```text
All referenced docs exist.
```

## Acceptance Criteria

- README provides a concise project entry point.
- Local setup doc can guide a fresh local run.
- Provider configuration doc explains API key setup safely.
- Sample workflow doc explains normal RAG usage.
- RAG evaluation guide explains core project metrics.
- Troubleshooting doc covers common local failures.
- Architecture doc links the system docs and diagrams.
- Docs contain no real secrets.
- No git commit is made.

## Open Design Notes

- Keep docs aligned with actual implemented features as the project evolves.
- Add screenshots only after the frontend UI exists.
- Add generated API docs later if the backend API surface grows large.
