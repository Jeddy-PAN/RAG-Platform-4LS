# Chat Citation Feedback Plan

> This is a lightweight module plan. It documents chat orchestration, provider boundaries, citation mapping, no-answer behavior, feedback capture, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Implement project-scoped RAG chat that retrieves context, generates cited answers through an OpenAI-compatible chat provider, stores conversations/messages/citations, and captures user feedback.

**Architecture:** Chat is a backend orchestration layer over retrieval, prompt assembly, LLM provider calls, persistence, and feedback. It always operates inside one selected project. Retrieval produces candidate chunks, prompt assembly converts them into context, answer generation calls the chat provider, citations are mapped back to stored chunks, and feedback records quality signals for later evaluation.

**Tech Stack:** FastAPI, SQLAlchemy, OpenAI-compatible chat API, custom retrieval engine, PostgreSQL, pytest.

---

## Scope

This plan covers:

- chat API contract
- conversation and message persistence
- OpenAI-compatible chat provider boundary
- prompt assembly contract
- retrieval-to-answer orchestration
- citation mapping
- no-answer behavior
- feedback API
- project isolation tests

This plan does not cover:

- retrieval algorithm internals
- document ingestion
- eval dashboard
- streaming responses
- multi-user auth
- frontend chat UI
- reranking

## File Changes

Provider modules:

- `apps/api/app/rag/providers/chat.py`
- `apps/api/app/rag/providers/types.py`

RAG modules:

- `apps/api/app/rag/prompting.py`
- `apps/api/app/rag/answering.py`
- `apps/api/app/rag/citations.py`

API and schemas:

- `apps/api/app/api/chat.py`
- `apps/api/app/api/feedback.py`
- `apps/api/app/schemas/chat.py`
- `apps/api/app/schemas/feedback.py`
- `apps/api/app/main.py`

Services:

- `apps/api/app/services/conversations.py`
- `apps/api/app/services/messages.py`
- `apps/api/app/services/feedback.py`

Tests:

- `apps/api/tests/test_chat_provider.py`
- `apps/api/tests/test_prompting.py`
- `apps/api/tests/test_answer_generation.py`
- `apps/api/tests/test_citations.py`
- `apps/api/tests/test_chat_api.py`
- `apps/api/tests/test_feedback_api.py`
- `apps/api/tests/test_chat_project_isolation.py`

## Mermaid Diagram

Chat orchestration diagram:

- `docs/superpowers/diagrams/chat-citation-feedback-flow.mmd`

## API Contract

### Send Chat Message

`POST /api/projects/{project_id}/chat/messages`

Purpose:

- create or continue a conversation
- run retrieval against the selected project
- generate an answer
- store user and assistant messages
- store citations

Request:

```json
{
  "conversation_id": "uuid-or-null",
  "message": "What does the handbook say about escalation?",
  "retrieval": {
    "mode": "hybrid",
    "top_k": 8,
    "vector_weight": 0.65,
    "keyword_weight": 0.35
  }
}
```

Response:

```json
{
  "conversation_id": "uuid",
  "user_message_id": "uuid",
  "assistant_message_id": "uuid",
  "answer": "Escalation should begin when...",
  "citations": [
    {
      "citation_index": 1,
      "chunk_id": "uuid",
      "document_id": "uuid",
      "document_name": "support-handbook.pdf",
      "page_number": 4,
      "quote": "Escalation should begin when..."
    }
  ],
  "retrieval_log_id": "uuid",
  "model": "configured-chat-model",
  "latency_ms": 2345
}
```

V1 response can be non-streaming. Streaming can be added after correctness and persistence are stable.

### List Conversations

`GET /api/projects/{project_id}/conversations`

Purpose:

- list project-scoped conversations

### Get Conversation

`GET /api/projects/{project_id}/conversations/{conversation_id}`

Purpose:

- fetch messages and citations for one project conversation

### Delete Conversation

`DELETE /api/projects/{project_id}/conversations/{conversation_id}`

Purpose:

- delete one project-scoped conversation and messages

### Submit Feedback

`POST /api/projects/{project_id}/feedback`

Purpose:

- mark an assistant answer as useful or not useful

Request:

```json
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "rating": "useful",
  "comment": "The answer cited the right section."
}
```

Response:

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "conversation_id": "uuid",
  "message_id": "uuid",
  "rating": "useful",
  "comment": "The answer cited the right section."
}
```

## Provider Boundary

Chat provider interface:

```python
generate_chat_completion(messages, model, temperature) -> ChatProviderResult
```

Provider config:

```text
LLM_PROVIDER
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

Rules:

- use OpenAI-compatible API first
- do not hard-code DeepSeek/OpenAI-specific assumptions into RAG orchestration
- do not log raw API keys
- provider errors become clear API errors
- provider response should include model name when available

## Prompt Assembly Contract

Input:

```text
project_id
user question
retrieved chunks
optional recent conversation messages
system prompt settings
```

Output:

```text
chat provider messages
context block
citation map
```

Prompt constraints:

- answer only from provided project context
- cite sources when making document-grounded claims
- if context is weak or absent, say the answer is not available in the selected knowledge base
- do not cite chunks that were not retrieved

Context format should make citation mapping explicit:

```text
[Source 1]
chunk_id: ...
document: ...
location: page/sheet/section
content: ...
```

## Citation Mapping

Citation mapping should be deterministic and database-backed.

Source of truth:

```text
retrieved chunk IDs
```

Stored citations:

```text
message_citations.project_id
message_citations.message_id
message_citations.chunk_id
message_citations.citation_index
message_citations.quote
message_citations.citation_metadata
```

Rules:

- assistant message citations must belong to the same `project_id`
- citations must reference retrieved chunks
- citations should preserve source metadata such as page number, sheet name, or section index
- quote can be a short excerpt from the chunk, not the full chunk

V1 acceptable citation strategy:

```text
Persist citations for the chunks included in the final answer context.
```

Later improvement:

```text
Ask the model to emit structured citation markers and map markers back to source chunks.
```

## No-Answer Behavior

No-answer behavior should trigger when:

- retrieval returns no chunks
- top retrieval scores are below threshold
- retrieved context does not support the question
- provider output lacks support from context

V1 strategy:

```text
If no chunks pass retrieval threshold, return a grounded refusal before calling the LLM.
If chunks exist, instruct the LLM to refuse when context is insufficient.
```

Example answer shape:

```text
I cannot answer this from the selected knowledge base. The retrieved documents do not contain enough relevant information.
```

This refusal should still be stored as an assistant message.

## Conversation Memory

V1 should include limited recent history:

```text
last N messages in the same conversation and project
```

Rules:

- history is only from the selected `project_id`
- history should not override retrieved document context
- avoid loading an unbounded conversation into the prompt

Suggested default:

```text
last 6 messages
```

## Project Isolation Rules

Every chat operation must validate `project_id`:

```python
conversation.project_id == project_id
message.project_id == project_id
chunk.project_id == project_id
feedback.project_id == project_id
```

Do not:

- continue a conversation from another project
- cite a chunk from another project
- attach feedback to a message from another project
- use conversation history from another project

## Persistence Flow

For a successful chat request:

1. validate project exists
2. create conversation if missing
3. validate existing conversation belongs to project
4. store user message
5. run retrieval
6. assemble prompt
7. call chat provider or return no-answer refusal
8. store assistant message
9. store message citations
10. return answer and citation details

For provider failure:

- keep the user message
- either store an assistant error message or return API error without assistant message
- preferred v1: return clear HTTP 503 and do not store assistant answer

## Error Contract

Use predictable HTTP statuses:

```text
400 empty message
400 invalid retrieval options
404 project not found
404 conversation not found within selected project
404 message not found within selected project
422 feedback rating invalid
503 chat provider unavailable
500 unexpected persistence or orchestration failure
```

Feedback-specific:

```text
Feedback should only target assistant messages.
```

## Implementation Sequence

1. Add chat provider result types.
2. Add OpenAI-compatible chat provider boundary.
3. Add prompt assembly module.
4. Add citation mapping module.
5. Add conversation service.
6. Add message service.
7. Add answer orchestration service.
8. Add chat schemas.
9. Add chat API routes.
10. Add feedback schemas.
11. Add feedback service.
12. Add feedback API route.
13. Register routers in FastAPI app.
14. Add provider tests with mocked API responses.
15. Add prompt assembly tests.
16. Add citation mapping tests.
17. Add chat API tests.
18. Add feedback API tests.
19. Add project isolation tests.

## Test Plan

### Chat Provider Tests

Verify:

- request shape is OpenAI-compatible
- configured model is used
- API key is not logged
- provider errors are converted into clear failures
- model name is captured when returned

### Prompting Tests

Verify:

- retrieved chunks become source blocks
- citation map includes chunk IDs
- recent conversation history is included only from same project
- empty retrieval produces no-answer path

### Answer Generation Tests

Verify:

- chat creates user and assistant messages
- retrieval is called with selected `project_id`
- no-answer refusal is returned when retrieval has no usable chunks
- provider is not called when pre-LLM refusal triggers
- provider output is stored as assistant message

### Citation Tests

Verify:

- citations reference chunks from the same project
- citations are linked to assistant message ID
- citations preserve document/source metadata
- cross-project chunk citation is rejected

### Feedback Tests

Verify:

- useful and not_useful ratings can be stored
- feedback targets only assistant messages
- feedback requires matching `project_id`
- feedback for another project's message returns 404

### Project Isolation Tests

Create:

```text
project_a conversation + chunk
project_b conversation + chunk
```

Verify:

- project A cannot continue project B conversation
- project A cannot cite project B chunk
- project A cannot attach feedback to project B message
- project A chat retrieval never uses project B chunks

## Verification Commands

Chat tests:

```bash
cd apps/api
pytest tests/test_chat_provider.py tests/test_prompting.py tests/test_answer_generation.py tests/test_citations.py -v
```

API/isolation tests:

```bash
cd apps/api
pytest tests/test_chat_api.py tests/test_feedback_api.py tests/test_chat_project_isolation.py -v
```

Full backend suite:

```bash
cd apps/api
pytest -v
```

Manual smoke test after implementation:

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/chat/messages \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":null,"message":"What does this knowledge base say about escalation?","retrieval":{"mode":"hybrid","top_k":5}}'
```

Expected:

```text
Response includes answer, assistant_message_id, citations, retrieval_log_id, model, and latency_ms.
```

## Acceptance Criteria

- Chat API creates project-scoped conversations and messages.
- Chat orchestration calls retrieval with the selected `project_id`.
- OpenAI-compatible chat provider is isolated behind an interface.
- Answers can include persisted citations linked to chunks.
- No-answer behavior works when retrieval is empty or weak.
- Feedback can be submitted for assistant messages.
- Tests prove conversations, citations, and feedback do not cross project boundaries.
- No git commit is made.

## Open Design Notes

- Non-streaming chat is acceptable for v1; streaming can be added after persistence and citations are correct.
- V1 citation strategy can persist the context chunks used for generation; structured model citation markers can come later.
- Feedback is intentionally simple now and can feed eval/metrics later.
