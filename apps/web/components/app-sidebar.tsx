"use client";

import { useState } from "react";
import type { AllConversation, Project, UUID } from "@/lib/types";

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className="chevron-icon"
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.15s" }}
    >
      <path d="M5 3L9 7L5 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

type AppSidebarProps = {
  projects: Project[];
  allConversations: AllConversation[];
  selectedProjectId: UUID | null;
  selectedConversationId: UUID | null;
  isLoadingProjects: boolean;
  onSelectProject: (projectId: UUID) => void;
  onSelectConversation: (conversation: AllConversation) => void;
  onDeleteConversation: (conversation: AllConversation) => void;
};

export function AppSidebar({
  projects,
  allConversations,
  selectedProjectId,
  selectedConversationId,
  isLoadingProjects,
  onSelectProject,
  onSelectConversation,
  onDeleteConversation
}: AppSidebarProps) {
  const [kbExpanded, setKbExpanded] = useState(false);
  const [chatsExpanded, setChatsExpanded] = useState(false);

  return (
    <aside className="app-sidebar">
      <section className="sidebar-section">
        <div className="sidebar-section-header" onClick={() => setKbExpanded((v) => !v)}>
          <div className="sidebar-section-label">
            <ChevronIcon expanded={kbExpanded} />
            <span>Knowledge Bases</span>
          </div>
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
        <div
          className="sidebar-section-header"
          onClick={() => setChatsExpanded((v) => !v)}
        >
          <div className="sidebar-section-label">
            <ChevronIcon expanded={chatsExpanded} />
            <span>Chats</span>
          </div>
          <span className="count">{allConversations.length}</span>
        </div>
        {chatsExpanded ? (
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
        ) : null}
      </section>
    </aside>
  );
}
