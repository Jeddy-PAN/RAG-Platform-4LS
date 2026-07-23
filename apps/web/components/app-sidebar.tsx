"use client";

import type { AllConversation, DocumentItem, Project, UUID } from "@/lib/types";
import { ProjectList } from "./project-list";

type AppSidebarProps = {
  projects: Project[];
  allConversations: AllConversation[];
  documentsByProject: Record<UUID, DocumentItem[]>;
  selectedProjectId: UUID | null;
  selectedConversationId: UUID | null;
  busyDocumentIds: Set<UUID>;
  expandedProjectIds: Set<UUID>;
  editMode: boolean;
  isLoadingProjects: boolean;
  loadingDocuments: Set<UUID>;
  onSelectProject: (projectId: UUID) => void;
  onToggleExpand: (projectId: UUID) => void;
  onSelectConversation: (conversation: AllConversation) => void;
  onDeleteConversation: (conversation: AllConversation) => void;
  onCreateProject: () => void;
  onToggleEditMode: () => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  onDeleteDocument: (projectId: UUID, document: DocumentItem) => void;
  onReindexDocument: (projectId: UUID, document: DocumentItem) => void;
  onClickKnowledgeBases: () => void;
};

export function AppSidebar({
  projects,
  allConversations,
  documentsByProject,
  selectedProjectId,
  selectedConversationId,
  busyDocumentIds,
  expandedProjectIds,
  editMode,
  isLoadingProjects,
  loadingDocuments,
  onSelectProject,
  onToggleExpand,
  onSelectConversation,
  onDeleteConversation,
  onCreateProject,
  onToggleEditMode,
  onRenameProject,
  onDeleteProject,
  onDeleteDocument,
  onReindexDocument,
  onClickKnowledgeBases
}: AppSidebarProps) {
  return (
    <aside className="app-sidebar">
      <section className="sidebar-section">
        <div
          className="sidebar-section-header"
          onClick={onClickKnowledgeBases}
        >
          <span>Knowledge Bases</span>
          <span className="count">{projects.length}</span>
        </div>
        <div className="sidebar-section-body">
          <div className="sidebar-heading">
            <div>
              <span className="sidebar-label">Projects</span>
            </div>
            <div className="sidebar-actions">
              <button aria-label="Add project" className="icon-button" onClick={onCreateProject} type="button">
                +
              </button>
              <button
                aria-label="Toggle project edit mode"
                className={`icon-button ${editMode ? "active" : ""}`}
                onClick={onToggleEditMode}
                type="button"
              >
                Edit
              </button>
            </div>
          </div>
          <ProjectList
            activeProjectId={selectedProjectId}
            busyDocumentIds={busyDocumentIds}
            documentsByProject={documentsByProject}
            editMode={editMode}
            expandedProjectIds={expandedProjectIds}
            loading={isLoadingProjects}
            loadingDocuments={loadingDocuments}
            onDeleteDocument={onDeleteDocument}
            onReindexDocument={onReindexDocument}
            onDeleteProject={onDeleteProject}
            onRenameProject={onRenameProject}
            onSelectProject={onSelectProject}
            onToggleExpand={onToggleExpand}
            projects={projects}
          />
        </div>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-section-header">
          <span>Chats</span>
          <span className="count">{allConversations.length}</span>
        </div>
        <div className="sidebar-section-body">
          {allConversations.length === 0 ? (
            <p className="sidebar-empty">No conversations yet</p>
          ) : (
            allConversations.map((conv) => (
              <div
                key={conv.id}
                className={`chat-sidebar-item ${selectedConversationId === conv.id ? "selected" : ""}`}
                onClick={() => onSelectConversation(conv)}
              >
                <span className="title">{conv.title ?? "Untitled"}</span>
                <span className="project-tag">{conv.project_name}</span>
                <button
                  className="delete-btn"
                  aria-label="Delete conversation"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteConversation(conv);
                  }}
                  type="button"
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}
