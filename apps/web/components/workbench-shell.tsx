"use client";

import { useEffect, useMemo, useState } from "react";
import { chatApi, documentsApi, feedbackApi, projectsApi, systemApi } from "@/lib/api";
import type {
  ChatMessage,
  DocumentItem,
  FeedbackRating,
  Project,
  SystemConfig,
  UUID
} from "@/lib/types";
import { ChatWorkspace } from "./chat-workspace";
import { ProjectSidebar } from "./project-sidebar";
import { TopBar } from "./top-bar";

const DOCUMENT_POLL_INTERVAL_MS = 2500;

function hasPendingDocuments(documents: DocumentItem[] | undefined): boolean {
  return documents?.some((document) => document.status === "uploaded" || document.status === "processing") ?? false;
}

export function WorkbenchShell() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [documentsByProject, setDocumentsByProject] = useState<Record<UUID, DocumentItem[]>>({});
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<UUID>>(new Set());
  const [loadingDocuments, setLoadingDocuments] = useState<Set<UUID>>(new Set());
  const [busyDocumentIds, setBusyDocumentIds] = useState<Set<UUID>>(new Set());
  const [activeProjectId, setActiveProjectId] = useState<UUID | null>(null);
  const [conversationId, setConversationId] = useState<UUID | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [editMode, setEditMode] = useState(false);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [systemConfig, setSystemConfig] = useState<SystemConfig | null>(null);
  const [sidebarError, setSidebarError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? null,
    [activeProjectId, projects]
  );

  useEffect(() => {
    void loadProjects();
    void loadSystemConfig();
  }, []);

  useEffect(() => {
    const projectIdsToPoll = [...expandedProjectIds].filter((projectId) =>
      hasPendingDocuments(documentsByProject[projectId])
    );
    if (projectIdsToPoll.length === 0) {
      return;
    }

    const intervalId = window.setInterval(() => {
      for (const projectId of projectIdsToPoll) {
        void loadDocuments(projectId, { silent: true });
      }
    }, DOCUMENT_POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [documentsByProject, expandedProjectIds]);

  async function loadProjects() {
    setIsLoadingProjects(true);
    setSidebarError(null);
    try {
      const nextProjects = await projectsApi.list();
      setProjects(nextProjects);
      if (!activeProjectId && nextProjects.length > 0) {
        const firstProjectId = nextProjects[0].id;
        setActiveProjectId(firstProjectId);
        setExpandedProjectIds((current) => new Set(current).add(firstProjectId));
        void loadDocuments(firstProjectId);
      }
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to load projects");
    } finally {
      setIsLoadingProjects(false);
    }
  }

  async function loadSystemConfig() {
    try {
      setSystemConfig(await systemApi.config());
    } catch {
      setSystemConfig(null);
    }
  }

  async function loadDocuments(projectId: UUID, options?: { silent?: boolean }) {
    if (!options?.silent) {
      setLoadingDocuments((current) => new Set(current).add(projectId));
    }
    try {
      const documents = await documentsApi.list(projectId);
      setDocumentsByProject((current) => ({ ...current, [projectId]: documents }));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to load documents");
    } finally {
      if (!options?.silent) {
        setLoadingDocuments((current) => {
          const next = new Set(current);
          next.delete(projectId);
          return next;
        });
      }
    }
  }

  async function handleCreateProject() {
    const name = window.prompt("Project name");
    if (!name?.trim()) {
      return;
    }

    try {
      const project = await projectsApi.create({ name: name.trim() });
      setProjects((current) => [project, ...current]);
      setActiveProjectId(project.id);
      setExpandedProjectIds((current) => new Set(current).add(project.id));
      setDocumentsByProject((current) => ({ ...current, [project.id]: [] }));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to create project");
    }
  }

  async function handleRenameProject(project: Project) {
    const name = window.prompt("New project name", project.name);
    if (!name?.trim() || name.trim() === project.name) {
      return;
    }

    try {
      const updated = await projectsApi.update(project.id, { name: name.trim() });
      setProjects((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to update project");
    }
  }

  async function handleDeleteProject(project: Project) {
    if (!window.confirm(`Delete project "${project.name}"?`)) {
      return;
    }

    try {
      await projectsApi.delete(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setDocumentsByProject((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
      if (activeProjectId === project.id) {
        setActiveProjectId(null);
        setMessages([]);
        setConversationId(null);
      }
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to delete project");
    }
  }

  function handleSelectProject(projectId: UUID) {
    setActiveProjectId(projectId);
    setConversationId(null);
    setMessages([]);
    setExpandedProjectIds((current) => new Set(current).add(projectId));
    if (!documentsByProject[projectId]) {
      void loadDocuments(projectId);
    }
  }

  function handleToggleExpand(projectId: UUID) {
    setExpandedProjectIds((current) => {
      const next = new Set(current);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
        if (!documentsByProject[projectId]) {
          void loadDocuments(projectId);
        }
      }
      return next;
    });
  }

  async function handleUpload(files: File[]) {
    if (!activeProjectId || files.length === 0) {
      return;
    }

    setIsUploading(true);
    setSidebarError(null);
    try {
      const uploaded = await Promise.all(files.map((file) => documentsApi.upload(activeProjectId, file)));
      setDocumentsByProject((current) => ({
        ...current,
        [activeProjectId]: [
          ...uploaded.map((item) => item.document),
          ...(current[activeProjectId] ?? [])
        ]
      }));
      setExpandedProjectIds((current) => new Set(current).add(activeProjectId));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to upload file");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleRefreshDocuments(projectId: UUID) {
    await loadDocuments(projectId);
  }

  async function handleReindexDocument(projectId: UUID, document: DocumentItem) {
    setBusyDocumentIds((current) => new Set(current).add(document.id));
    setSidebarError(null);
    try {
      await documentsApi.reindex(projectId, document.id);
      await loadDocuments(projectId);
      setExpandedProjectIds((current) => new Set(current).add(projectId));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to reindex document");
    } finally {
      setBusyDocumentIds((current) => {
        const next = new Set(current);
        next.delete(document.id);
        return next;
      });
    }
  }

  async function handleDeleteDocument(projectId: UUID, document: DocumentItem) {
    if (!window.confirm(`Delete file "${document.filename}"?`)) {
      return;
    }

    setBusyDocumentIds((current) => new Set(current).add(document.id));
    setSidebarError(null);
    try {
      await documentsApi.delete(projectId, document.id);
      setDocumentsByProject((current) => ({
        ...current,
        [projectId]: (current[projectId] ?? []).filter((item) => item.id !== document.id)
      }));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to delete document");
    } finally {
      setBusyDocumentIds((current) => {
        const next = new Set(current);
        next.delete(document.id);
        return next;
      });
    }
  }

  async function handleSend(message: string) {
    if (!activeProjectId) {
      return;
    }

    const localUserMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message
    };

    setMessages((current) => [...current, localUserMessage]);
    setIsSending(true);
    setChatError(null);

    try {
      const response = await chatApi.sendMessage(activeProjectId, {
        conversation_id: conversationId,
        message,
        retrieval: {
          mode: "hybrid",
          top_k: 8,
          vector_weight: 0.65,
          keyword_weight: 0.35
        }
      });

      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: response.assistant_message_id,
          role: "assistant",
          content: response.answer,
          citations: response.citations,
          assistantMessageId: response.assistant_message_id,
          latencyMs: response.latency_ms,
          model: response.model
        }
      ]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "Unable to send message");
    } finally {
      setIsSending(false);
    }
  }

  async function handleFeedback(messageId: UUID, rating: FeedbackRating) {
    if (!activeProjectId || !conversationId) {
      return;
    }

    await feedbackApi.submit(activeProjectId, {
      conversation_id: conversationId,
      message_id: messageId,
      rating
    });
  }

  return (
    <div className="app-shell">
      <TopBar activeProject={activeProject} systemConfig={systemConfig} />
      <div className="workbench-layout">
        <ProjectSidebar
          activeProjectId={activeProjectId}
          busyDocumentIds={busyDocumentIds}
          documentsByProject={documentsByProject}
          editMode={editMode}
          error={sidebarError}
          expandedProjectIds={expandedProjectIds}
          isLoadingProjects={isLoadingProjects}
          isUploading={isUploading}
          loadingDocuments={loadingDocuments}
          onCreateProject={handleCreateProject}
          onDeleteDocument={handleDeleteDocument}
          onDeleteProject={handleDeleteProject}
          onRefreshDocuments={handleRefreshDocuments}
          onReindexDocument={handleReindexDocument}
          onRenameProject={handleRenameProject}
          onSelectProject={handleSelectProject}
          onToggleEditMode={() => setEditMode((value) => !value)}
          onToggleExpand={handleToggleExpand}
          onUpload={handleUpload}
          projects={projects}
        />
        <ChatWorkspace
          activeProject={activeProject}
          conversationId={conversationId}
          error={chatError}
          isSending={isSending}
          messages={messages}
          onFeedback={handleFeedback}
          onSend={handleSend}
        />
      </div>
    </div>
  );
}
