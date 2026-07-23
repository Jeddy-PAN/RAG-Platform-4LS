"use client";

import { useState } from "react";
import type { AllConversation, ChatMessage, DocumentItem, FeedbackRating, Project, UUID } from "@/lib/types";
import { ErrorState } from "./error-state";
import { MessageComposer } from "./message-composer";
import { MessageList } from "./message-list";
import { SidebarUploadZone } from "./sidebar-upload-zone";
import { StatusBadge } from "./status-badge";

type DashboardView = "kb-home" | "project-detail" | "chat";

type DashboardPanelProps = {
  view: DashboardView;
  projects: Project[];
  selectedProject: Project | null;
  selectedConversation: AllConversation | null;
  documents: DocumentItem[];
  projectConversations: AllConversation[];
  messages: ChatMessage[];
  conversationId: UUID | null;
  isSending: boolean;
  isUploading: boolean;
  error: string | null;
  onCreateProject: () => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  onSelectProject: (projectId: UUID) => void;
  onUpload: (files: File[]) => void;
  onDeleteDocument: (projectId: UUID, document: DocumentItem) => void;
  onReindexDocument: (projectId: UUID, document: DocumentItem) => void;
  onRefreshDocuments: (projectId: UUID) => void;
  onStartChat: () => void;
  onSelectConversation: (conversation: AllConversation) => void;
  onDeleteConversation: (conversation: AllConversation) => void;
  onSend: (message: string) => Promise<void>;
  onFeedback: (messageId: UUID, rating: FeedbackRating) => Promise<void>;
  onUploadToProject: (files: File[]) => void;
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function DashboardPanel({
  view,
  projects,
  selectedProject,
  selectedConversation,
  documents,
  projectConversations,
  messages,
  conversationId,
  isSending,
  isUploading,
  error,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  onSelectProject,
  onUpload,
  onDeleteDocument,
  onReindexDocument,
  onRefreshDocuments,
  onStartChat,
  onSelectConversation,
  onDeleteConversation,
  onSend,
  onFeedback,
  onUploadToProject
}: DashboardPanelProps) {
  const [composerMessage, setComposerMessage] = useState("");

  if (view === "kb-home") {
    return (
      <main className="dashboard">
        <div className="kb-home">
          <div className="kb-home-header">
            <h2>Knowledge Bases</h2>
            <button className="btn btn-primary" onClick={onCreateProject} type="button">
              + New Project
            </button>
          </div>
          {projects.length === 0 ? (
            <div className="dashboard-empty">
              <span className="empty-icon">📁</span>
              <p>No projects yet. Create your first knowledge base.</p>
            </div>
          ) : (
            <div className="project-card-grid">
              {projects.map((project) => (
                <div
                  key={project.id}
                  className="project-card"
                  onClick={() => onSelectProject(project.id)}
                >
                  <h3>{project.name}</h3>
                  <div className="card-meta">
                    <span>{project.description ?? "No description"}</span>
                  </div>
                  <div className="card-meta">
                    <span>Created {formatDate(project.created_at)}</span>
                  </div>
                  <div className="card-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn btn-sm"
                      onClick={() => onRenameProject(project)}
                      type="button"
                    >
                      Rename
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => onDeleteProject(project)}
                      type="button"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    );
  }

  if (view === "project-detail" && selectedProject) {
    return (
      <main className="dashboard">
        <div className="project-detail">
          <div className="detail-header">
            <div>
              <h2>{selectedProject.name}</h2>
              {selectedProject.description ? (
                <p style={{ margin: "4px 0 0", color: "var(--muted)", fontSize: 14 }}>{selectedProject.description}</p>
              ) : null}
            </div>
            <div className="detail-actions">
              <button className="btn btn-primary" onClick={onStartChat} type="button">
                Start Chat
              </button>
              <button className="btn" onClick={() => onRenameProject(selectedProject)} type="button">
                Rename
              </button>
              <button className="btn btn-danger" onClick={() => onDeleteProject(selectedProject)} type="button">
                Delete Project
              </button>
            </div>
          </div>

          <section className="detail-section">
            <h3>Files ({documents.length})</h3>
            <SidebarUploadZone disabled={false} isUploading={isUploading} onUpload={onUploadToProject} />
            {documents.length === 0 ? (
              <p className="sidebar-empty">No files uploaded</p>
            ) : (
              <table className="file-list-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Size</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td>{doc.filename}</td>
                      <td><StatusBadge status={doc.status} /></td>
                      <td style={{ color: "var(--muted)", fontSize: 12 }}>
                        {doc.file_size_bytes > 0 ? `${(doc.file_size_bytes / 1024).toFixed(0)} KB` : "—"}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <button
                          className="btn btn-sm"
                          onClick={() => onReindexDocument(selectedProject.id, doc)}
                          disabled={doc.status !== "indexed"}
                          type="button"
                        >
                          Reindex
                        </button>
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={() => onDeleteDocument(selectedProject.id, doc)}
                          style={{ marginLeft: 6 }}
                          type="button"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="detail-section">
            <h3>Conversations ({projectConversations.length})</h3>
            {projectConversations.length === 0 ? (
              <p className="sidebar-empty">No conversations in this project</p>
            ) : (
              <div className="conversation-list">
                {projectConversations.map((conv) => (
                  <div
                    key={conv.id}
                    className="conversation-list-item"
                    onClick={() => onSelectConversation(conv)}
                  >
                    <span className="conv-title">{conv.title ?? "Untitled"}</span>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <span className="conv-time">{formatRelative(conv.updated_at)}</span>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteConversation(conv);
                        }}
                        type="button"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>
    );
  }

  if (view === "chat") {
    const convProjectName = selectedConversation?.project_name ?? (selectedProject?.name ?? "Chat");
    const disabled = !selectedProject && !selectedConversation;

    return (
      <main className="dashboard" style={{ padding: "28px", overflow: "hidden", display: "grid", placeItems: messages.length === 0 ? "center" : "stretch" }}>
        {messages.length === 0 ? (
          <div className="dashboard-empty">
            <span className="empty-icon">💬</span>
            <h2 style={{ margin: 0, fontSize: 18 }}>New Conversation</h2>
            <p style={{ margin: 0 }}>{convProjectName}</p>
            <MessageComposer
              disabled={disabled}
              isSending={isSending}
              onSend={onSend}
            />
          </div>
        ) : (
          <div className="chat-view">
            <div className="conversation-header">
              <span>Chat</span>
              <strong>{convProjectName}</strong>
            </div>
            <MessageList
              conversationId={conversationId}
              isSending={isSending}
              messages={messages}
              onFeedback={onFeedback}
            />
            <MessageComposer disabled={disabled} isSending={isSending} onSend={onSend} />
          </div>
        )}
        {error ? <ErrorState message={error} /> : null}
      </main>
    );
  }

  return null;
}
