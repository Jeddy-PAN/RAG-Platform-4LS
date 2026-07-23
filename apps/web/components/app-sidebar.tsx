"use client";

import { useState } from "react";
import type { AllConversation, Project, UUID } from "@/lib/types";

type AppSidebarProps = {
  projects: Project[];
  allConversations: AllConversation[];
  selectedProjectId: UUID | null;
  selectedConversationId: UUID | null;
  isLoadingProjects: boolean;
  onSelectProject: (projectId: UUID) => void;
  onSelectConversation: (conversation: AllConversation) => void;
  onDeleteConversation: (conversation: AllConversation) => void;
  onClickKnowledgeBases: () => void;
};

export function AppSidebar({
  projects,
  allConversations,
  selectedProjectId,
  selectedConversationId,
  isLoadingProjects,
  onSelectProject,
  onSelectConversation,
  onDeleteConversation,
  onClickKnowledgeBases
}: AppSidebarProps) {
  const [kbExpanded, setKbExpanded] = useState(true);

  return (
    <aside className="app-sidebar">
      <section className="sidebar-section">
        <div
          className="sidebar-section-header"
          onClick={() => setKbExpanded((v) => !v)}
        >
          <span>Knowledge Bases</span>
          <span className="count">{projects.length}</span>
        </div>
        {kbExpanded ? (
          <div className="sidebar-section-body">
            {isLoadingProjects ? (
              <p className="sidebar-empty">Loading...</p>
            ) : projects.length === 0 ? (
              <p className="sidebar-empty">No projects yet</p>
            ) : (
              projects.map((project) => (
                <div
                  key={project.id}
                  className={`chat-sidebar-item ${selectedProjectId === project.id ? "selected" : ""}`}
                  onClick={() => onSelectProject(project.id)}
                >
                  <span className="title">{project.name}</span>
                </div>
              ))
            )}
          </div>
        ) : null}
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
