# Project And Document API Plan

> This is a lightweight module plan. It documents API contracts, service boundaries, data flow, validation rules, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Implement project management and document upload APIs that create project-scoped document records and ingestion jobs.

**Architecture:** The backend exposes REST endpoints for projects and documents. Project APIs manage knowledge-base containers. Document APIs validate uploads, store files locally, create `documents` rows, and enqueue or record ingestion jobs for the worker pipeline. Actual parsing/chunking/embedding is handled by the later ingestion pipeline plan.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic schemas, local filesystem storage, RQ job enqueueing, pytest.

---

## Scope

This plan covers:

- project CRUD APIs
- document upload API
- document listing/detail APIs
- document delete and re-index request APIs
- supported file validation
- local storage path convention
- ingestion job row creation
- RQ enqueue boundary
- project-scoped API tests

This plan does not cover:

- parsing PDF/DOCX/TXT/XLSX
- chunking
- embeddings
- indexing
- retrieval
- chat
- frontend upload UI

## File Changes

API routes:

- `apps/api/app/api/projects.py`
- `apps/api/app/api/documents.py`
- `apps/api/app/api/__init__.py`
- `apps/api/app/main.py`

Schemas:

- `apps/api/app/schemas/project.py`
- `apps/api/app/schemas/document.py`

Services:

- `apps/api/app/services/projects.py`
- `apps/api/app/services/documents.py`
- `apps/api/app/services/storage.py`
- `apps/api/app/services/ingestion_jobs.py`

Worker boundary:

- `apps/api/app/workers/enqueue.py`

Tests:

- `apps/api/tests/test_projects_api.py`
- `apps/api/tests/test_documents_api.py`
- `apps/api/tests/test_document_storage.py`
- `apps/api/tests/test_document_project_isolation.py`

## API Contract

### Projects

`POST /api/projects`

Purpose:

- create a project / knowledge base

Request:

```json
{
  "name": "Client Research",
  "description": "Documents for client research and planning"
}
```

Response:

```json
{
  "id": "uuid",
  "name": "Client Research",
  "description": "Documents for client research and planning",
  "created_at": "iso-datetime",
  "updated_at": "iso-datetime"
}
```

`GET /api/projects`

Purpose:

- list projects ordered by latest update or creation time

`GET /api/projects/{project_id}`

Purpose:

- fetch one project

`PATCH /api/projects/{project_id}`

Purpose:

- update project name or description

`DELETE /api/projects/{project_id}`

Purpose:

- delete a project and all project-owned data through cascade behavior

### Documents

`POST /api/projects/{project_id}/documents`

Purpose:

- upload a supported file into one project
- create a document record
- create an ingestion job record
- enqueue ingestion work if Redis/RQ is available

Request:

```text
multipart/form-data
file=<PDF | DOCX | TXT | XLSX>
```

Response:

```json
{
  "document": {
    "id": "uuid",
    "project_id": "uuid",
    "filename": "handbook.pdf",
    "content_type": "application/pdf",
    "file_size_bytes": 123456,
    "status": "uploaded"
  },
  "ingestion_job": {
    "id": "uuid",
    "project_id": "uuid",
    "document_id": "uuid",
    "status": "queued"
  }
}
```

`GET /api/projects/{project_id}/documents`

Purpose:

- list documents for one project only

Query options:

```text
status=uploaded|processing|indexed|failed
limit=50
offset=0
```

`GET /api/projects/{project_id}/documents/{document_id}`

Purpose:

- fetch document metadata for one project

`DELETE /api/projects/{project_id}/documents/{document_id}`

Purpose:

- delete document, sections, chunks, and ingestion jobs for one project
- delete stored source file if it exists

`POST /api/projects/{project_id}/documents/{document_id}/reindex`

Purpose:

- create a new ingestion job for an existing document
- mark the document as `processing` or keep status as-is until worker starts, depending on final implementation choice

## Supported File Types

Initial supported extensions:

```text
.pdf
.docx
.txt
.xlsx
```

Validation rules:

- reject unsupported extensions with HTTP 400
- reject empty files with HTTP 400
- sanitize original filename before using it in storage paths
- do not trust client-provided content type alone
- preserve original filename in metadata

Optional v1 limit:

```text
max upload size = 50 MB
```

This can be enforced at application level first and revisited later.

## Storage Convention

Use local filesystem storage in v1.

Recommended path shape:

```text
data/uploads/{project_id}/{document_id}/{safe_filename}
```

Why:

- project and document boundaries are visible on disk
- duplicate filenames do not collide
- later migration to object storage can preserve the same logical key

Store this value in:

```text
documents.storage_path
```

## Ingestion Job Boundary

Document upload should not parse the file synchronously.

Upload flow:

1. validate project exists
2. validate file
3. store file
4. create `documents` row with status `uploaded`
5. create `ingestion_jobs` row with status `queued`
6. enqueue worker job with `job_id`, `project_id`, `document_id`
7. return document and job metadata

If Redis/RQ enqueue fails:

- keep the document row
- mark ingestion job as `failed` or return a clear 503 depending on implementation preference
- do not silently report success if no worker job can run

Preferred v1 behavior:

```text
If enqueue fails, return HTTP 503 and mark ingestion job failed with error_message.
```

## Project Isolation Rules

Every document endpoint must use both `project_id` and `document_id` when operating on a single document:

```python
where(Document.id == document_id, Document.project_id == project_id)
```

Do not fetch a document only by `document_id` in request handlers.

This prevents:

- opening another project's document by guessed UUID
- deleting another project's document
- reindexing another project's document

## Service Boundaries

`projects` service:

- create project
- list projects
- get project
- update project
- delete project

`storage` service:

- validate filename
- build storage path
- write uploaded file
- delete stored file

`documents` service:

- validate project exists
- create document record
- list project documents
- get project document
- delete project document
- request reindex

`ingestion_jobs` service:

- create job row
- update job status on enqueue failure
- provide job metadata for API responses

`workers/enqueue` boundary:

- enqueue ingestion job into RQ
- hide Redis/RQ details from API route handlers

## Error Contract

Use predictable HTTP statuses:

```text
400 unsupported file type, empty file, invalid payload
404 project not found
404 document not found within selected project
409 duplicate project name
413 upload too large
503 ingestion queue unavailable
```

Error response shape:

```json
{
  "detail": "Unsupported file type: .exe"
}
```

FastAPI's default `HTTPException` shape is enough for v1.

## Mermaid Diagram

Detailed flow diagram:

- `docs/superpowers/diagrams/project-document-upload-flow.mmd`

## Implementation Sequence

1. Add project schemas.
2. Add document schemas.
3. Add project service functions.
4. Add storage service functions.
5. Add ingestion job service functions.
6. Add RQ enqueue helper.
7. Add project API routes.
8. Add document API routes.
9. Register routers in `main.py`.
10. Add project API tests.
11. Add document upload tests.
12. Add project isolation tests for document access.
13. Add storage path tests.
14. Run backend test suite.

## Test Plan

### Project API Tests

Verify:

- create project
- list projects
- get project
- update project
- delete project
- duplicate project name returns 409
- missing project returns 404

### Document API Tests

Verify:

- upload `.pdf`, `.docx`, `.txt`, `.xlsx`
- unsupported file type returns 400
- empty upload returns 400
- upload creates document row
- upload creates ingestion job row
- upload calls enqueue helper
- list documents only returns selected project documents
- get document requires matching `project_id`
- delete document requires matching `project_id`
- reindex requires matching `project_id`

### Storage Tests

Verify:

- unsafe filenames are sanitized
- storage path includes `project_id` and `document_id`
- duplicate original filenames do not collide
- delete ignores missing files safely

### Queue Boundary Tests

Verify:

- enqueue helper receives `job_id`, `project_id`, and `document_id`
- enqueue failure updates job status or returns 503 according to chosen behavior

## Verification Commands

Backend tests:

```bash
cd apps/api
pytest tests/test_projects_api.py tests/test_documents_api.py tests/test_document_storage.py tests/test_document_project_isolation.py -v
```

Full backend suite:

```bash
cd apps/api
pytest -v
```

Manual API smoke test after implementation:

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo Project","description":"Upload smoke test"}'
```

Then upload a file:

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/documents \
  -F "file=@sample.txt"
```

## Acceptance Criteria

- Project CRUD APIs work.
- Document upload accepts PDF, DOCX, TXT, and XLSX.
- Unsupported files are rejected.
- Uploaded files are stored under a project/document scoped path.
- Upload creates a document row.
- Upload creates an ingestion job row.
- Upload enqueues ingestion work through a single helper boundary.
- Document list/detail/delete/reindex APIs are project-scoped.
- Tests prove document APIs do not cross project boundaries.
- No git commit is made.

## Open Design Notes

- The final max upload size can be adjusted after testing with real work documents.
- The ingestion enqueue failure policy should be implemented explicitly; v1 preference is HTTP 503 plus failed job status.
- Local filesystem storage is enough for v1; the storage service should keep the path abstraction clean for future MinIO/object storage.
