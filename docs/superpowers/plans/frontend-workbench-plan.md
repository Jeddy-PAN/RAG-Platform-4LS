# Frontend Workbench Plan

> This is a lightweight module plan. It documents layout structure, interaction flows, component boundaries, API usage, UI states, and verification goals. Full source code should be generated during implementation, not embedded here.

**Goal:** Build a simple, lightweight single-screen RAG workbench with project/file management on the left and chat as the main experience on the right.

**Architecture:** The frontend starts as one primary app surface instead of a multi-page dashboard. A top bar anchors the app. A left sidebar manages projects, project files, and drag-and-drop upload. The right workspace centers the chat experience. Retrieval Playground remains available through a lightweight floating button and can open as a separate route, drawer, or overlay depending on implementation fit.

**Tech Stack:** Next.js, React, TypeScript, Tailwind CSS, shadcn-style component patterns, browser fetch API or a small typed API client.

---

## Design Read

This should feel like a lightweight local knowledge assistant, not a dashboard suite.

UI character:

```text
minimal, calm, translucent, chat-first, project-aware
```

Key direction:

- top bar remains visible
- left sidebar is split vertically
- upper sidebar is mainly project/file navigation
- lower sidebar is drag-and-drop upload
- right side is the main chat area
- Retrieval Playground is secondary and accessed through a floating button

Avoid:

- heavy dashboard feel
- many page tabs
- dense analytics UI in v1
- oversized cards
- marketing hero sections
- complicated admin navigation

## Scope

This plan covers v1 frontend surface:

- main single-screen workbench
- top app bar
- left project/file sidebar
- project add/edit/delete interactions
- collapsible project file lists
- drag-and-drop upload area
- right-side chat workspace
- citation and feedback display
- floating Retrieval Playground entry
- minimal project/status indicators

This plan does not cover:

- full Eval Dashboard UI
- full metrics dashboard
- full document viewer
- full admin/settings UI
- multi-user auth UI
- complex layout customization

## File Changes

App routes:

- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/retrieval/page.tsx`

Components:

- `apps/web/components/top-bar.tsx`
- `apps/web/components/workbench-shell.tsx`
- `apps/web/components/project-sidebar.tsx`
- `apps/web/components/project-list.tsx`
- `apps/web/components/project-row.tsx`
- `apps/web/components/project-file-tree.tsx`
- `apps/web/components/sidebar-upload-zone.tsx`
- `apps/web/components/chat-workspace.tsx`
- `apps/web/components/chat-empty-state.tsx`
- `apps/web/components/message-list.tsx`
- `apps/web/components/message-composer.tsx`
- `apps/web/components/citation-list.tsx`
- `apps/web/components/feedback-controls.tsx`
- `apps/web/components/retrieval-floating-button.tsx`
- `apps/web/components/retrieval-controls.tsx`
- `apps/web/components/retrieval-results.tsx`
- `apps/web/components/status-badge.tsx`
- `apps/web/components/error-state.tsx`
- `apps/web/components/loading-state.tsx`

API/client:

- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `apps/web/lib/format.ts`

Styles:

- `apps/web/app/globals.css`

## Mermaid Diagram

Frontend layout and workflow diagram:

- `docs/superpowers/diagrams/frontend-workbench-navigation.mmd`

## Layout Structure

Primary screen:

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar                                                      │
├───────────────────────┬──────────────────────────────────────┤
│ Left Sidebar          │ Right Chat Workspace                 │
│                       │                                      │
│ Projects / Files 60%  │ Empty: title + centered input        │
│                       │ After first message: conversation    │
│ Upload Zone 40%       │ with composer fixed near bottom      │
└───────────────────────┴──────────────────────────────────────┘
```

Recommended proportions:

```text
top bar height: compact and fixed
left sidebar width: 280-340px desktop
left sidebar upper area: about 60%
left sidebar lower upload area: about 40%
right side: remaining width
```

Mobile behavior can collapse the sidebar behind a menu button.

## Top Bar

Responsibilities:

- app name or compact brand label
- optional active project indicator
- minimal global controls

Rules:

- keep top bar visually light
- do not add user/account controls in v1
- do not duplicate project actions that belong in the sidebar

## Left Sidebar

The left sidebar has two sections.

### Upper Section: Projects And Files

Approximate height:

```text
60%
```

Contains:

- Projects header
- lightweight add button using plus icon
- lightweight edit mode button using edit icon
- project rows
- collapsible file lists under each project

Interactions:

- click project row: focus/preview project
- double-click project row: select active project
- click disclosure icon: expand/collapse project files
- click plus icon: create project
- click edit icon: toggle project edit mode
- in edit mode, each project row exposes edit/delete actions

Project row states:

```text
default
hover
focused
selected
editing
delete-confirming
```

File tree:

- files appear nested under their project
- each file shows name and ingestion status
- file rows are lightweight, not full cards
- failed files should expose a concise error hint

### Lower Section: Upload Zone

Approximate height:

```text
40%
```

Purpose:

- drag files into the active project
- support click-to-select file upload
- show supported file types
- show upload/ingestion status

Rules:

- upload requires an active selected project
- disabled state when no project is selected
- accepted types: PDF, DOCX, TXT, XLSX
- upload zone should be visually quiet and always available

## Right Chat Workspace

The right side is the primary experience.

### Empty Chat State

Before the first user message:

- show an elegant, simple title
- show a short subtitle only if useful
- show a translucent input box
- show send button attached to or adjacent to input

Suggested title style:

```text
Ask your local knowledge base
```

Keep copy minimal. Do not explain features in paragraphs.

### Active Conversation State

After the first message:

- input/composer moves to the lower part of the right panel
- conversation appears above
- messages render in a calm, readable layout
- citations are visible under assistant answers
- feedback controls appear near assistant answers

Composer behavior:

- transparent or lightly translucent surface
- clear send button
- keyboard submit
- disabled state while sending
- no layout jump when answer streams or loads

V1 can be non-streaming, but the UI should tolerate a loading assistant state.

## Retrieval Playground Entry

Retrieval Playground is secondary in v1.

Use:

```text
lightweight floating button
```

Placement:

- bottom-right or right-middle of chat workspace
- should not cover composer
- visible enough to discover, quiet enough not to dominate

Behavior options:

```text
Option A: navigate to /retrieval
Option B: open a right-side overlay
Option C: open a modal/drawer
```

Recommended v1:

```text
Option A: route to /retrieval
```

Reason:

- simplest to implement
- keeps chat workspace clean
- avoids complex overlay state

## API Client Contract

`lib/api.ts` should group calls by domain:

```text
projectsApi
documentsApi
chatApi
retrievalApi
metricsApi
```

Rules:

- centralize backend base URL
- parse JSON consistently
- surface API errors as typed frontend errors
- avoid duplicating fetch logic inside components

Environment:

```text
NEXT_PUBLIC_API_BASE_URL
```

## State Model

Frontend v1 state:

```text
projects
expandedProjectIds
activeProjectId
editMode
activeConversationId
pendingUploads
chatMessages
isSendingMessage
```

Keep state local or in a small store. If prop drilling becomes awkward, use a lightweight Zustand store.

Do not introduce complex server-state tooling unless the implementation becomes noisy. TanStack Query can be added later.

## UI State Rules

Every primary area should handle:

- loading
- empty
- error
- success

Examples:

```text
No projects -> sidebar shows add project action
No active project -> upload zone disabled and chat composer disabled
Project has no files -> expanded file list shows empty hint
Upload failed -> file/upload row shows error status
Provider unavailable -> chat shows inline error near composer
Retrieval failed -> retrieval page shows error state
```

## Visual Direction

Use a minimal product UI:

- neutral background
- light translucent chat composer
- subtle borders
- restrained shadows
- one accent color
- icon-first sidebar actions
- compact project rows
- no nested cards

Specific visual notes:

- plus icon represents add project
- edit icon toggles project edit mode
- delete should appear only in edit mode or confirmation state
- selected project should be obvious but not loud
- file status should be readable without relying only on color

## Accessibility And Interaction Rules

- icon buttons need labels/tooltips
- double-click selection must have an accessible single-click or keyboard equivalent
- file upload must support click-to-select
- form labels must not rely on placeholders
- disabled states must explain what is missing
- focus states must be visible
- send button must be reachable by keyboard
- upload drop zone must not be the only way to upload files

## Implementation Sequence

1. Add shared frontend types.
2. Add API client wrapper.
3. Add top bar.
4. Add workbench shell layout.
5. Add project sidebar layout.
6. Add project list and project row states.
7. Add project add/edit/delete interactions.
8. Add collapsible project file tree.
9. Add sidebar upload zone.
10. Add chat workspace empty state.
11. Add message composer.
12. Add message list.
13. Add citation list.
14. Add feedback controls.
15. Add active conversation layout transition.
16. Add Retrieval Playground floating button.
17. Add minimal retrieval route/page.
18. Add loading/empty/error states.
19. Run lint/build checks.

## Test And Verification Plan

Build checks:

```bash
cd apps/web
pnpm lint
pnpm build
```

Manual workflow checks:

1. Open `/`.
2. Create a project with the plus button.
3. Toggle edit mode with the edit icon.
4. Edit and delete controls appear per project row.
5. Expand a project to show files.
6. Double-click a project row to select it.
7. Upload a TXT file through the lower sidebar upload zone.
8. Confirm file appears under the selected project.
9. Ask the first chat question from the centered empty state.
10. Confirm composer moves to the lower chat area.
11. Confirm conversation appears above the composer.
12. Confirm citations and feedback render after an answer.
13. Use floating Retrieval Playground button.
14. Confirm retrieval page opens and can run a query.

Responsive checks:

- desktop: sidebar and chat side by side
- tablet: sidebar can narrow or collapse
- mobile: sidebar collapses behind menu, chat remains primary

Focus checks:

- add project button
- edit mode button
- project row
- file tree disclosure
- upload zone
- chat composer
- send button
- floating retrieval button

## Acceptance Criteria

- Main frontend opens as a single lightweight workbench.
- Top bar remains visible.
- Left sidebar is split into project/file area and upload area.
- Projects can be added from a plus icon.
- Project edit mode exposes edit/delete actions per row.
- Project files can be collapsed and expanded.
- A project can be selected, with double-click supported and accessible fallback available.
- Upload zone accepts supported files for the active project.
- Right workspace starts with a simple title and translucent composer.
- After first message, composer moves lower and conversation occupies the main area.
- Citations and feedback controls render for assistant answers.
- Retrieval Playground is accessible through a lightweight floating button.
- Frontend builds successfully.
- No git commit is made.

## Open Design Notes

- The UI should prioritize chat and file/project context over dashboards.
- Retrieval Playground can start as a route for simplicity; overlay/drawer can come later.
- Metrics can appear as subtle status text later, not as a full dashboard in v1.
