# Ingestion Pipeline Plan

> This is a lightweight module plan. It documents pipeline boundaries, data contracts, state transitions, failure behavior, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Convert uploaded project documents into searchable, embedded chunks stored in PostgreSQL with pgvector and full-text search support.

**Architecture:** Ingestion runs asynchronously in the RQ worker. The worker loads an ingestion job, parses the stored document, normalizes sections, chunks text, generates embeddings through an OpenAI-compatible provider, writes chunks to PostgreSQL, and updates document/job status. API upload stays fast and does not perform parsing or embedding synchronously.

**Tech Stack:** RQ worker, SQLAlchemy, PyMuPDF, python-docx, openpyxl, native TXT reader, OpenAI-compatible embedding API, pgvector, PostgreSQL full-text search.

---

## Scope

This plan covers:

- parser adapter interface
- PDF parser
- DOCX parser
- TXT parser
- XLSX parser
- normalized section contract
- deterministic chunking
- content hashing
- embedding provider boundary
- ingestion job state transitions
- chunk/index writes
- failure handling
- ingestion tests

This plan does not cover:

- file upload API
- project CRUD
- retrieval algorithms
- answer generation
- reranking
- frontend ingestion UI
- OCR or scanned PDF support

## File Changes

Parser modules:

- `apps/api/app/ingestion/parsers/base.py`
- `apps/api/app/ingestion/parsers/pdf.py`
- `apps/api/app/ingestion/parsers/docx.py`
- `apps/api/app/ingestion/parsers/txt.py`
- `apps/api/app/ingestion/parsers/xlsx.py`
- `apps/api/app/ingestion/parsers/__init__.py`

Pipeline modules:

- `apps/api/app/ingestion/chunker.py`
- `apps/api/app/ingestion/hashing.py`
- `apps/api/app/ingestion/pipeline.py`
- `apps/api/app/ingestion/status.py`

Provider modules:

- `apps/api/app/rag/providers/embeddings.py`
- `apps/api/app/rag/providers/types.py`

Worker modules:

- `apps/api/app/workers/tasks.py`
- `apps/api/app/workers/worker.py`

Tests:

- `apps/api/tests/test_parsers.py`
- `apps/api/tests/test_chunker.py`
- `apps/api/tests/test_embedding_provider.py`
- `apps/api/tests/test_ingestion_pipeline.py`
- `apps/api/tests/test_ingestion_failure.py`

## Mermaid Diagram

Pipeline diagram:

- `docs/superpowers/diagrams/ingestion-pipeline-flow.mmd`

## Input Contract

The ingestion worker receives:

```text
job_id
project_id
document_id
```

The worker must load the document using both:

```python
document.id == document_id
document.project_id == project_id
```

Do not load documents by `document_id` alone.

## Normalized Section Contract

Each parser returns a list of normalized sections:

```text
NormalizedSection
- section_index
- text
- source_metadata
```

Recommended metadata:

```text
PDF: page_number
DOCX: paragraph_start / paragraph_end when useful
TXT: line_start / line_end when useful
XLSX: sheet_name, row_start, row_end
```

Rules:

- section text must be stripped of obvious surrounding whitespace
- empty sections are discarded
- original source location should be preserved when possible
- parser output should be deterministic for the same file

## Parser Behavior

PDF parser:

- use PyMuPDF
- extract text page by page
- one section per page for v1
- preserve `page_number`

DOCX parser:

- use python-docx
- extract non-empty paragraphs
- group paragraphs into sections if needed
- preserve paragraph indexes when practical

TXT parser:

- decode as UTF-8 by default
- handle UTF-8 BOM
- normalize line endings
- preserve line range metadata when practical

XLSX parser:

- use openpyxl
- read visible sheets
- convert rows to text records
- preserve `sheet_name` and row ranges
- skip fully empty rows

## Chunking Contract

Input:

```text
project_id
document_id
section_id
section text
chunk_size
chunk_overlap
```

Output:

```text
ChunkCandidate
- chunk_index
- text
- token_count or char_count
- content_hash
- source_metadata
```

Defaults:

```text
chunk_size = 800 approximate tokens or character-based fallback
chunk_overlap = 120 approximate tokens or character-based fallback
```

V1 can use a simple deterministic character/word fallback if tokenizer integration is not ready. The important requirement is that chunking is stable and testable.

## Content Hashing

Each chunk should have a stable hash based on:

```text
project_id
document_id
chunk text
source metadata
chunker version
```

Purpose:

- avoid duplicate chunks in reindex flows
- support idempotent ingestion later
- help debug chunk changes after chunker tuning

## Embedding Provider Boundary

Provider interface:

```python
embed_texts(texts: list[str]) -> list[list[float]]
```

Configuration:

```text
EMBEDDING_PROVIDER
EMBEDDING_BASE_URL
EMBEDDING_API_KEY
EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
```

Rules:

- batch texts where practical
- validate returned vector count equals input text count
- validate each vector dimension matches configured/database dimension
- do not log raw API keys
- provider-specific errors should become clear ingestion failure messages

## Database Write Strategy

For one ingestion job:

1. mark job `running`
2. mark document `processing`
3. parse document
4. insert document sections
5. chunk sections
6. call embedding provider
7. delete prior chunks for the same document if this is a reindex
8. insert new chunks with embeddings
9. let DB trigger populate `search_vector`
10. mark job `completed`
11. mark document `indexed`

Write behavior should be transactional where practical:

- parser and embedding calls happen outside long DB transactions
- final section/chunk replacement happens in a short DB transaction
- status updates should still record failure if a later step fails

## State Transitions

Document statuses:

```text
uploaded -> processing -> indexed
uploaded -> processing -> failed
indexed -> processing -> indexed
indexed -> processing -> failed
```

Ingestion job statuses:

```text
queued -> running -> completed
queued -> running -> failed
```

Failure rules:

- failed job stores `error_message`
- failed document stores `error_message`
- failed ingestion should not leave document marked `processing`
- if old indexed chunks exist and reindex fails, prefer preserving old chunks until replacement succeeds

## Idempotency And Reindexing

Initial v1 behavior:

- upload creates first ingestion job
- reindex creates a new ingestion job for the same document
- final replacement deletes old sections/chunks for the document and inserts new ones

Preferred safety rule:

```text
Do not delete old chunks until new parse/chunk/embed work has succeeded.
```

This prevents a failed reindex from destroying a working knowledge base.

## Error Handling

Common failure cases:

```text
file missing from storage
unsupported parser extension
parser cannot extract text
document contains no usable text
embedding API unavailable
embedding response count mismatch
embedding dimension mismatch
database insert failure
```

Each failure should:

- mark job failed
- mark document failed only when no previous indexed version should remain active
- store a human-readable error message
- avoid leaking secrets

## Implementation Sequence

1. Add parser base types.
2. Add PDF parser.
3. Add DOCX parser.
4. Add TXT parser.
5. Add XLSX parser.
6. Add parser registry by extension.
7. Add chunker.
8. Add content hashing helper.
9. Add embedding provider interface.
10. Add OpenAI-compatible embedding provider.
11. Add ingestion pipeline orchestration.
12. Add worker task wrapper.
13. Wire RQ enqueue target to worker task.
14. Add parser tests.
15. Add chunker tests.
16. Add embedding provider tests with mocked API responses.
17. Add full ingestion pipeline test with mocked embeddings.
18. Add failure handling tests.

## Test Plan

### Parser Tests

Verify:

- PDF parser returns one section per text page
- DOCX parser returns non-empty paragraph text
- TXT parser handles UTF-8 and normalizes line endings
- XLSX parser returns sheet and row metadata
- empty documents produce a controlled failure

### Chunker Tests

Verify:

- chunking is deterministic
- chunk overlap is applied
- chunk metadata preserves source metadata
- tiny text returns one chunk
- empty text returns no chunks or controlled validation error

### Embedding Provider Tests

Verify:

- request shape matches OpenAI-compatible embeddings API
- output vector count equals input count
- dimension mismatch raises a clear error
- API errors become ingestion failure messages

### Pipeline Tests

Verify:

- job status moves from queued to running to completed
- document status moves to indexed
- sections are inserted
- chunks are inserted with embeddings
- chunks keep `project_id`
- reindex preserves old chunks if new processing fails
- ingestion never loads a document by `document_id` alone

## Verification Commands

Parser/chunker tests:

```bash
cd apps/api
pytest tests/test_parsers.py tests/test_chunker.py -v
```

Embedding/pipeline tests:

```bash
cd apps/api
pytest tests/test_embedding_provider.py tests/test_ingestion_pipeline.py tests/test_ingestion_failure.py -v
```

Full backend suite:

```bash
cd apps/api
pytest -v
```

Manual worker smoke test after implementation:

```bash
docker compose up postgres redis backend worker
```

Then upload a small TXT file through the document API and confirm:

```text
document.status = indexed
ingestion_job.status = completed
chunks exist for the selected project_id
```

## Acceptance Criteria

- Worker can process queued ingestion jobs.
- PDF, DOCX, TXT, and XLSX files produce normalized sections.
- Sections are chunked deterministically.
- Chunks include stable content hashes.
- Embedding provider is isolated behind an interface.
- Embedding dimension mismatches fail clearly.
- Successful ingestion creates document sections and embedded chunks.
- Chunk rows are scoped by `project_id`.
- Failed ingestion records a clear error and does not leave stale `processing` status.
- Reindex failure does not destroy previously working chunks.
- No git commit is made.

## Open Design Notes

- Character/word-based chunking is acceptable for v1; tokenizer-aware chunking can be added after the full RAG loop works.
- XLSX text representation should be simple first; table-aware retrieval can be improved later.
- OCR and scanned PDFs are explicitly out of scope for v1.
