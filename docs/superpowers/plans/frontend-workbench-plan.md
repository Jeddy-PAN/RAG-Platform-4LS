# Frontend Workbench Plan

> This is a lightweight module plan. It documents frontend layout, page responsibilities, interaction flows, API usage, UI states, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Provide a simple local RAG workbench where project files, chat, retrieval inspection, eval runs, and metrics are available without turning the product into a heavy dashboard suite.

**Current status:** The main workbench, Retrieval Playground, Eval page, and Metrics page are implemented as separate Next.js routes with shared project context patterns and a lightweight visual style.

**Tech Stack:** Next.js, React, TypeScript, global CSS, browser fetch API, small typed API client.

---

## Design Read

The frontend should feel like a lightweight local knowledge assistant.

UI character:

```text
minimal, calm, translucent, chat-first, project-aware
```

Key direction:

- top bar remains visible
- main page avoids full-page vertical growth on desktop
- left sidebar uses local scrolling
- project/file navigation stays lightweight
- upload zone remains in the lower sidebar
- chat is the primary experience
- Retrieval, Eval, and Metrics are secondary tools reachable through floating links

Avoid:

- heavy dashboard feel
- oversized cards
- nested cards
- marketing hero sections
- always-visible destructive actions
- fixed warning banners for transient errors

## Implemented Routes

Main routes:

- `/` main chat workbench
- `/retrieval` Retrieval Playground
- `/eval` Eval workspace
- `/metrics` Chat metrics dashboard

Shared infrastructure:

- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `apps/web/lib/format.ts`
- `apps/web/app/globals.css`

## Main Workbench

Primary screen:

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar                                                      │
├───────────────────────┬──────────────────────────────────────┤
│ Left Sidebar          │ Right Chat Workspace                 │
│                       │                                      │
│ Projects / Files      │ Empty: title + centered composer     │
│ local scroll          │                                      │
│                       │ Active: conversation + composer      │
│ Upload Zone           │ Floating Retrieval/Eval/Metrics      │
└───────────────────────┴──────────────────────────────────────┘
```

Desktop behavior:

- top bar stays visible
- workbench fits the viewport
- project/file list scrolls inside the sidebar
- chat conversation scrolls inside the right panel
- page-level scroll should not be required just to reach the composer or floating tool links

### Left Sidebar

The sidebar has two sections.

Upper section:

- projects list
- lightweight `+` button for add project
- lightweight edit icon to toggle edit mode
- project rows
- file tree under the expanded project
- local scrolling when many projects/files exist

Lower section:

- drag-and-drop upload zone
- click-to-select upload
- disabled state when no active project is selected
- accepted file types: PDF, DOCX, TXT, XLSX

Project interactions:

- click project row: focus project
- double-click project row: select active project
- disclosure icon: expand project files
- only one project should be expanded at a time
- edit mode exposes project edit/delete actions
- file edit/delete actions stay hidden until the file/project editing mode is active

### Right Chat Workspace

Before the first user message:

- show a simple title
- show a translucent composer
- keep copy minimal

After the first user message:

- conversation appears above
- composer moves to the lower area
- composer auto-grows with text
- manual textarea resizing is disabled
- send button stays beside the composer and vertically centered
- assistant answers show citations and feedback controls

Floating tool links:

- Retrieval
- Eval
- Metrics

These should stay available without covering the composer.

## Retrieval Playground

Purpose:

- inspect raw retrieval behavior
- tune retrieval settings before changing chat or eval behavior
- compare vector, keyword, hybrid, and reranker behavior

User flow:

1. choose a project
2. enter a natural-language query
3. select retrieval mode
4. tune top-k and hybrid weights
5. optionally enable reranker
6. inspect chunks, scores, metadata, and retrieval log ID

Input meaning:

- the query input is the same kind of question a user would ask in chat
- the page returns retrieved context only, not a final LLM answer

Difference from Eval:

- Retrieval Playground is for one-off inspection and tuning.
- Eval is for repeatable datasets, metrics, history, comparison, and export.

## Eval Workspace

The Eval page should be compact and locally scrollable.

Left side:

- projects
- datasets
- local scrolling
- add/edit/delete through lightweight header actions and modals
- no always-visible destructive actions

Right side:

- selected dataset context
- tabs for `Questions` and `History`
- run configuration
- result details
- run compare panel when runs are selected

Transient warnings:

- use a top-centered toast-style bubble
- do not keep warnings fixed in the page layout

Dataset/question actions:

- create dataset through modal
- edit/delete dataset through modal or contextual action
- create question through modal
- delete question uses the same destructive button style as dataset delete

Eval run controls:

- retrieval mode
- top-k
- vector weight
- keyword weight
- reranker enabled
- reranker candidate limit
- LLM judge enabled

History behavior:

- list previous runs
- allow loading a run
- allow selecting runs for compare
- compare up to a small bounded number of runs
- export run CSV/JSON
- export compare CSV

## Metrics Workspace

Purpose:

- show whether chat requests are fast, cited, and traceable
- provide quick debugging links back to retrieval logs

Current metrics:

- request count
- average total latency
- average retrieval latency
- average generation latency
- average citation count
- recent chat requests

The page is intentionally lightweight. It should not become the primary app surface.

## API Client Contract

`lib/api.ts` groups calls by domain:

```text
projectsApi
documentsApi
chatApi
feedbackApi
retrievalApi
evalApi
metricsApi
systemApi
```

Rules:

- centralize backend base URL
- parse JSON consistently
- surface API errors as frontend errors
- avoid duplicating fetch logic inside components

Environment:

```text
NEXT_PUBLIC_API_BASE_URL
```

## State Model

Core main-page state:

```text
projects
documentsByProject
expandedProjectId
activeProjectId
editMode
activeConversationId
chatMessages
pendingUploads
isSendingMessage
```

Eval state:

```text
selectedProjectId
selectedDatasetId
questions
runs
activeRun
compareRunIds
runConfig
toastMessage
activeTab
```

Keep state local while the app remains small. Introduce server-state tooling only if manual loading/error state becomes noisy.

## UI State Rules

Every primary area should handle:

- loading
- empty
- error
- success

Examples:

- no projects: sidebar shows add project action
- no active project: upload zone and chat composer are disabled
- project has no files: expanded file list shows empty hint
- upload failed: file row shows failed status
- provider unavailable: chat shows inline error near composer
- retrieval failed: retrieval page shows error state
- eval dataset missing: top-centered toast warning
- metrics empty: summary shows zero/null values and empty recent list

## Accessibility And Interaction Rules

- icon buttons need labels or accessible names
- double-click selection needs a single-click or keyboard fallback
- file upload must support click-to-select
- form labels must not rely only on placeholders
- disabled states should explain what is missing
- focus states must be visible
- send button must be keyboard reachable
- local scroll regions should not trap keyboard navigation

## Verification Commands

Frontend:

```bash
cd apps/web
pnpm lint
node --experimental-strip-types --test lib/*.test.mjs
```

Manual route checks:

```text
GET /
GET /retrieval
GET /eval
GET /metrics
```

Manual workflow checks:

1. Create and select a project.
2. Upload a supported file.
3. Expand projects and confirm only one remains expanded.
4. Send a chat message and confirm composer behavior.
5. Open Retrieval and run a query.
6. Open Eval, create a dataset/question, run eval, and view history.
7. Select runs for compare and export.
8. Open Metrics and inspect recent chat requests.

## Acceptance Criteria

- Main frontend opens as a lightweight workbench.
- Top bar remains visible.
- Main page desktop layout does not require page-level scroll for core controls.
- Left sidebar uses local scrolling for long project/file lists.
- Only one project is expanded at a time.
- Upload zone accepts supported files for the active project.
- Chat composer auto-grows and keeps send aligned.
- Citations and feedback controls render for assistant answers.
- Retrieval page exposes retrieval tuning and result inspection.
- Eval page exposes datasets, questions, history, run settings, compare, and export.
- Metrics page exposes chat metrics and recent request rows.
- Frontend checks pass.

## Future Work

- Mobile sidebar collapse refinement.
- Document preview/source viewer.
- Prompt/model settings page.
- Better charting for metrics trends.
- Stronger visual linking from metrics rows to retrieval log detail.
