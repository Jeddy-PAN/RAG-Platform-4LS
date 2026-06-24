# Local Enterprise RAG Platform Design

## Goal

Build a real local work tool for long-term personal and project use while learning RAG engineering in depth. The platform ingests uploaded project documents, builds isolated knowledge bases, supports RAG question answering with citations, and exposes retrieval/evaluation details so the user can understand and improve the RAG pipeline.

This is not a one-page RAG demo. It is a small production-style system with clear module boundaries, async ingestion, hybrid retrieval, feedback, logs, and Docker Compose deployment.

## Confirmed Stack

- Backend: FastAPI + Python
- Frontend: Next.js + React + TypeScript
- Database: PostgreSQL
- Vector store: pgvector
- Keyword search: PostgreSQL full-text search
- Queue: Redis + RQ
- LLM: API key first, OpenAI-compatible chat provider
- Embedding: API embedding first, local embedding optional
- Local model: Ollama optional
- RAG core: custom lightweight RAG pipeline
- Document parsing: PyMuPDF, python-docx, native TXT reader, openpyxl
- Evaluation: custom lightweight eval and logs
- Deployment: Docker Compose
- Auth: no user login in v1
- Isolation: multi-project / multi-knowledge-base isolation through project_id

## Explicit Non-Goals For V1

- Multi-user login
- RBAC
- Qdrant
- Elasticsearch or OpenSearch
- Kubernetes
- LangChain or LangGraph as the primary RAG runtime
- Langfuse or Phoenix integration
- Complex OCR and scanned PDF extraction
- Public SaaS deployment

These can be added later through stable interfaces, but the first version focuses on a reliable local RAG workbench.

## Architecture

The system has five runtime services:

Architecture diagram:

- `docs/superpowers/diagrams/overall-runtime-architecture.mmd`

1. Frontend
   - Next.js application.
   - Provides project management, document management, RAG chat, retrieval playground, and dashboard views.

2. Backend API
   - FastAPI service.
   - Owns REST APIs, database access, provider configuration, retrieval orchestration, answer generation, and eval endpoints.

3. Worker
   - RQ worker process.
   - Runs document parsing, chunking, embedding, and indexing jobs asynchronously.

4. PostgreSQL
   - Stores application data, document metadata, chunks, embeddings through pgvector, full-text search vectors, conversations, feedback, and eval records.

5. Redis
   - Stores RQ queues and job metadata.

## Core Modules

### 1. Project / Knowledge Base

A project is the main isolation boundary. Each project represents one local knowledge base, such as a work project, design project, client project, research topic, or enterprise document set.

Every document, chunk, conversation, retrieval log, feedback record, and eval run belongs to one project.

Rules:

- Every RAG query must include a project_id.
- Retrieval only searches chunks with the same project_id.
- Conversations belong to one project.
- Eval datasets and eval runs belong to one project.

### 2. Document Upload

V1 supports:

- PDF
- DOCX
- TXT
- XLSX

The upload API stores the original file, creates a document record, and enqueues an ingestion job. The frontend shows ingestion status.

### 3. Document Parsing

Parser adapters convert source files into normalized text sections.

Initial parser choices:

- PDF: PyMuPDF
- DOCX: python-docx
- TXT: native Python reader
- XLSX: openpyxl

The parser output should preserve basic metadata:

- source file name
- page number when available
- sheet name for XLSX
- section index
- extracted text

### 4. Chunking

The custom chunker splits normalized text into chunks. V1 should support configurable chunk size and overlap at project or indexing-job level.

Suggested defaults:

- chunk_size: 800 tokens or approximate characters if tokenizer is not available
- chunk_overlap: 120 tokens or approximate characters

Each chunk stores:

- project_id
- document_id
- chunk_index
- text
- source metadata
- token or character count
- content hash

### 5. Embedding And Indexing

Embedding uses an OpenAI-compatible API provider first. Local embedding is optional for later.

The indexing worker:

1. reads parsed chunks
2. calls embedding provider
3. stores vector in pgvector
4. stores PostgreSQL full-text search vector
5. marks document status as indexed or failed

Provider configuration should not be hard-coded to one vendor. It should support settings like:

- embedding_base_url
- embedding_api_key
- embedding_model
- embedding_dimensions

### 6. Hybrid Retrieval

V1 retrieval combines:

- vector search through pgvector
- keyword search through PostgreSQL full-text search

The backend merges scores into a hybrid ranking.

Suggested retrieval modes:

- vector
- keyword
- hybrid

The retrieval playground should expose:

- query
- retrieval mode
- top_k
- vector weight
- keyword weight
- similarity threshold
- returned chunks
- raw scores
- final fused score

Reranking is not required in the first implementation, but the retrieval interface should allow adding a reranker later.

### 7. Answer Generation

The answer generator uses:

- selected project
- user query
- retrieved chunks
- optional conversation history
- system prompt
- OpenAI-compatible chat API

The answer must include citations that map back to chunk and document records.

The answer generator should support no-answer behavior:

- If retrieved context is weak or unrelated, the assistant should say it cannot answer from the provided knowledge base.
- The response should avoid unsupported claims when citations are missing.

### 8. Citation

Citation is a first-class feature. Each generated answer stores citation references to the chunks used.

Frontend citation behavior:

- show cited document name
- show page, sheet, or section when available
- show quoted chunk preview
- allow opening source details

### 9. Feedback

Users can mark answers as useful or not useful. Optional notes can be added later.

Feedback stores:

- project_id
- conversation_id
- message_id
- rating
- optional comment
- created_at

This supports later evaluation and quality tracking.

### 10. Eval And Logs

V1 uses custom lightweight evaluation and logs instead of external observability tools.

The system should record:

- query text
- retrieval mode
- retrieved chunks
- retrieval scores
- generated answer
- citations
- retrieval latency
- generation latency
- total latency
- model name
- feedback

Initial eval metrics:

- top-k hit rate
- citation coverage
- answer latency
- retrieval latency
- useful feedback rate
- no-answer refusal rate

Eval datasets can be simple rows with:

- question
- expected document or chunk
- optional expected answer notes
- should_answer boolean

## Data Model

Initial tables:

- projects
- documents
- document_sections
- chunks
- conversations
- messages
- message_citations
- retrieval_logs
- retrieval_log_chunks
- feedback
- eval_datasets
- eval_questions
- eval_runs
- eval_results
- ingestion_jobs
- app_settings

Important schema rules:

- Core tables include project_id.
- Retrieval queries always filter by project_id.
- Chunks include both embedding vector and full-text search vector.
- Documents have ingestion status.
- Logs should be queryable by project, model, retrieval mode, and time.

## API Shape

Suggested endpoint groups:

- /api/projects
- /api/projects/{project_id}/documents
- /api/projects/{project_id}/ingestion-jobs
- /api/projects/{project_id}/chat
- /api/projects/{project_id}/retrieval
- /api/projects/{project_id}/conversations
- /api/projects/{project_id}/feedback
- /api/projects/{project_id}/eval
- /api/settings/models
- /api/health

Important API behavior:

- Chat APIs should support streaming eventually, but non-streaming is acceptable for the first backend milestone.
- Retrieval APIs should return debug details for learning and tuning.
- Document upload should return a document and job status.

## Frontend Workbench

V1 uses a lightweight single-screen workbench instead of a heavy multi-page dashboard.

Primary layout:

- top bar
- left sidebar
- right chat workspace
- floating Retrieval Playground entry

Left sidebar:

- upper area for Projects and expandable project files
- plus icon for adding projects
- edit icon for toggling project edit mode
- per-project edit/delete actions in edit mode
- collapsible files under each project
- lower area for drag-and-drop document upload

Right chat workspace:

- simple title and translucent input before the first message
- after first message, conversation appears above and composer moves near the bottom
- assistant answers can show citations and feedback controls

Retrieval Playground:

- accessed through a lightweight floating button
- can open as a route first
- compares vector, keyword, and hybrid retrieval
- shows returned chunks and scores

Later pages:

- Eval Dashboard
- Prompt / Model Settings
- Activity / Logs
- Document Viewer
- Admin / Backup

## Configuration

Use environment variables for provider settings:

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=replace-me
LLM_MODEL=example-chat-model

EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://api.example.com/v1
EMBEDDING_API_KEY=replace-me
EMBEDDING_MODEL=example-embedding-model
EMBEDDING_DIMENSIONS=1024

DATABASE_URL=postgresql+psycopg://rag:rag@postgres:5432/rag
REDIS_URL=redis://redis:6379/0
```

Do not commit real API keys.

## Docker Compose Services

V1 Compose services:

- frontend
- backend
- worker
- postgres
- redis

Optional later:

- ollama
- minio
- backup job
- observability service

## MVP Development Order

1. Repository and Docker Compose skeleton
2. Backend project structure and health API
3. PostgreSQL schema and migrations
4. Project CRUD
5. Document upload and storage
6. RQ ingestion job lifecycle
7. Parsers for PDF, DOCX, TXT, XLSX
8. Chunking
9. Embedding provider adapter
10. pgvector and full-text indexing
11. Retrieval API with vector, keyword, and hybrid modes
12. Chat API with citations
13. Feedback logging
14. Lightweight eval dataset and run APIs
15. Single-screen frontend workbench
16. Documentation and sample data

## Risks And Mitigations

- Embedding dimension mismatch
  - Store provider model and dimensions. Validate dimensions before inserting vectors.

- Document parsing quality varies
  - Keep parser adapters isolated. Store extracted sections so parsing can be inspected and improved.

- Hybrid score tuning can be unclear
  - Expose raw vector score, keyword score, and fused score in Retrieval Playground.

- Project isolation bugs can pollute answers
  - Make project_id required in all retrieval and chat queries. Add tests for cross-project isolation.

- API providers differ slightly despite OpenAI compatibility
  - Keep LLM and embedding provider adapters isolated. Start with one working provider, then add others.

## Acceptance Criteria For V1

- User can create multiple projects.
- User can upload PDF, DOCX, TXT, and XLSX into a selected project.
- Ingestion runs asynchronously and shows status.
- Documents are parsed, chunked, embedded, and indexed.
- User can ask questions against one project without retrieving other projects' content.
- Answers include citations linked to source chunks.
- Retrieval Playground can compare vector, keyword, and hybrid search.
- Feedback is recorded for answers.
- Basic logs include query, retrieved chunks, scores, answer, citations, latency, and model.
- The system runs locally with Docker Compose.
