"use client";

import { useEffect, useMemo, useState } from "react";
import { chatApi, conversationsApi, documentsApi, feedbackApi, projectsApi, systemApi } from "@/lib/api";
import type {
  AllConversation,
  ChatMessage,
  DocumentItem,
  FeedbackRating,
  Project,
  SystemConfig,
  UUID
} from "@/lib/types";
import { AppSidebar } from "./app-sidebar";
import { DashboardPanel } from "./dashboard-panel";
import { TopBar } from "./top-bar";

type DashboardView = "kb-home" | "project-detail" | "chat";

const DOCUMENT_POLL_INTERVAL_MS = 2500;

function hasPendingDocuments(documents: DocumentItem[] | undefined): boolean {
  return documents?.some((doc) => doc.status === "uploaded" || doc.status === "processing") ?? false;
}

export function WorkbenchShell() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [documentsByProject, setDocumentsByProject] = useState<Record<UUID, DocumentItem[]>>({});
  const [loadingDocuments, setLoadingDocuments] = useState<Set<UUID>>(new Set());
  const [busyDocumentIds, setBusyDocumentIds] = useState<Set<UUID>>(new Set());
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [systemConfig, setSystemConfig] = useState<SystemConfig | null>(null);
  const [sidebarError, setSidebarError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);

  // Dashboard view state
  const [view, setView] = useState<DashboardView>("kb-home");
  const [selectedProjectId, setSelectedProjectId] = useState<UUID | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<UUID | null>(null);

  // Chat state
  const [conversationId, setConversationId] = useState<UUID | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // All conversations for sidebar
  const [allConversations, setAllConversations] = useState<AllConversation[]>([]);

  // Project-scoped conversations
  const [projectConversations, setProjectConversations] = useState<AllConversation[]>([]);

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === selectedProjectId) ?? null,
    [selectedProjectId, projects]
  );

  const selectedConversation = useMemo(
    () => allConversations.find((c) => c.id === selectedConversationId) ?? null,
    [selectedConversationId, allConversations]
  );

  const currentDocuments = useMemo(
    () => (selectedProjectId ? documentsByProject[selectedProjectId] ?? [] : []),
    [selectedProjectId, documentsByProject]
  );

  // Load initial data
  useEffect(() => {
    void loadProjects();
    void loadAllConversations();
    void loadSystemConfig();
  }, []);

  // Poll for document status changes on the selected project
  useEffect(() => {
    if (!selectedProjectId) return;
    if (!hasPendingDocuments(documentsByProject[selectedProjectId])) return;

    const intervalId = window.setInterval(() => {
      if (selectedProjectId) {
        void loadDocuments(selectedProjectId, { silent: true });
      }
    }, DOCUMENT_POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [documentsByProject, selectedProjectId]);

  // ── Data Loaders ──────────────────────────────────────────

  async function loadProjects() {
    setIsLoadingProjects(true);
    setSidebarError(null);
    try {
      const nextProjects = await projectsApi.list();
      setProjects(nextProjects);
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to load projects");
    } finally {
      setIsLoadingProjects(false);
    }
  }

  async function loadAllConversations() {
    try {
      setAllConversations(await conversationsApi.listAll());
    } catch {
      // silently ignore
    }
  }

  async function loadProjectConversations(projectId: UUID) {
    try {
      setProjectConversations(await conversationsApi.listByProject(projectId));
    } catch {
      setProjectConversations([]);
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

  // ── Project Actions ───────────────────────────────────────

  async function handleCreateProject() {
    const name = window.prompt("Project name");
    if (!name?.trim()) return;
    try {
      const project = await projectsApi.create({ name: name.trim() });
      setProjects((current) => [project, ...current]);
      setSelectedProjectId(project.id);

      setDocumentsByProject((current) => ({ ...current, [project.id]: [] }));
      setView("project-detail");
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to create project");
    }
  }

  async function handleRenameProject(project: Project) {
    const name = window.prompt("New project name", project.name);
    if (!name?.trim() || name.trim() === project.name) return;
    try {
      const updated = await projectsApi.update(project.id, { name: name.trim() });
      setProjects((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to update project");
    }
  }

  async function handleDeleteProject(project: Project) {
    if (!window.confirm(`Delete project "${project.name}"? This will permanently remove all documents, uploaded files, conversations, and evaluation data.`)) return;
    try {
      await projectsApi.delete(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setDocumentsByProject((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
      setAllConversations((current) => current.filter((c) => c.project_id !== project.id));
      if (selectedProjectId === project.id) {
        setSelectedProjectId(null);
        setView("kb-home");
        setMessages([]);
        setConversationId(null);
      }
    } catch (error) {
      setSidebarError(error instanceof Error ? error.message : "Unable to delete project");
    }
  }

  // ── Sidebar Navigation ────────────────────────────────────

  function handleSelectProject(projectId: UUID) {
    setSelectedProjectId(projectId);
    setSelectedConversationId(null);
    setMessages([]);
    setConversationId(null);
    setView("project-detail");

    if (!documentsByProject[projectId]) {
      void loadDocuments(projectId);
    }
    void loadProjectConversations(projectId);
  }

  async function handleSelectConversation(conversation: AllConversation) {
    setSelectedConversationId(conversation.id);
    setSelectedProjectId(conversation.project_id);
    setView("chat");
    setConversationId(conversation.id);
    setChatError(null);

    // Load messages for this conversation
    try {
      const detail = await conversationsApi.get(conversation.project_id, conversation.id);
      setMessages(
        detail.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          assistantMessageId: m.role === "assistant" ? m.id : undefined
        }))
      );
    } catch {
      setMessages([]);
    }

    // Preload documents for the project
    if (!documentsByProject[conversation.project_id]) {
      void loadDocuments(conversation.project_id);
    }
    void loadProjectConversations(conversation.project_id);
  }

  async function handleDeleteConversation(conversation: AllConversation) {
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await conversationsApi.delete(conversation.project_id, conversation.id);
      setAllConversations((current) => current.filter((c) => c.id !== conversation.id));
      setProjectConversations((current) => current.filter((c) => c.id !== conversation.id));
      if (selectedConversationId === conversation.id) {
        setSelectedConversationId(null);
        setMessages([]);
        setConversationId(null);
      }
    } catch {
      setSidebarError("Unable to delete conversation");
    }
  }

  // ── Document Actions ──────────────────────────────────────

  async function handleUpload(files: File[]) {
    if (!selectedProjectId || files.length === 0) return;
    setIsUploading(true);
    setSidebarError(null);
    try {
      const uploaded = await Promise.all(files.map((file) => documentsApi.upload(selectedProjectId, file)));
      setDocumentsByProject((current) => ({
        ...current,
        [selectedProjectId]: [
          ...uploaded.map((item) => item.document),
          ...(current[selectedProjectId] ?? [])
        ]
      }));

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
    if (!window.confirm(`Delete file "${document.filename}"?`)) return;
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

  // ── Chat Actions ──────────────────────────────────────────

  function handleStartChat() {
    setSelectedConversationId(null);
    setMessages([]);
    setConversationId(null);
    setView("chat");
  }

  function getChatProjectId(): UUID | null {
    if (selectedProjectId) return selectedProjectId;
    if (selectedConversation) return selectedConversation.project_id;
    return null;
  }

  async function handleSend(message: string) {
    const projectId = getChatProjectId();
    if (!projectId) return;

    const localUserMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message
    };

    setMessages((current) => [...current, localUserMessage]);
    setIsSending(true);
    setChatError(null);

    try {
      const response = await chatApi.sendMessage(projectId, {
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

      // Refresh conversation lists
      void loadAllConversations();
      if (selectedProjectId) {
        void loadProjectConversations(selectedProjectId);
      }
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "Unable to send message");
    } finally {
      setIsSending(false);
    }
  }

  async function handleFeedback(messageId: UUID, rating: FeedbackRating) {
    const projectId = getChatProjectId();
    if (!projectId || !conversationId) return;
    await feedbackApi.submit(projectId, {
      conversation_id: conversationId,
      message_id: messageId,
      rating
    });
  }

  // ── Render ────────────────────────────────────────────────

  // Determine the active project for TopBar context
  const topBarProject = selectedProject ?? (selectedConversation
    ? projects.find((p) => p.id === selectedConversation.project_id) ?? null
    : null);

  return (
    <div className="app-shell">
      <TopBar activeProject={topBarProject} systemConfig={systemConfig} />
      <div className="workbench-layout">
        <AppSidebar
          allConversations={allConversations}
          isLoadingProjects={isLoadingProjects}
          projects={projects}
          selectedConversationId={selectedConversationId}
          selectedProjectId={selectedProjectId}
          onDeleteConversation={handleDeleteConversation}
          onSelectConversation={handleSelectConversation}
          onSelectProject={handleSelectProject}
        />
        <DashboardPanel
          conversationId={conversationId}
          documents={currentDocuments}
          error={chatError}
          isSending={isSending}
          isUploading={isUploading}
          messages={messages}
          onCreateProject={handleCreateProject}
          onDeleteConversation={handleDeleteConversation}
          onDeleteDocument={handleDeleteDocument}
          onDeleteProject={handleDeleteProject}
          onFeedback={handleFeedback}
          onRefreshDocuments={handleRefreshDocuments}
          onReindexDocument={handleReindexDocument}
          onRenameProject={handleRenameProject}
          onSelectConversation={handleSelectConversation}
          onSelectProject={handleSelectProject}
          onSend={handleSend}
          onStartChat={handleStartChat}
          onUpload={handleUpload}
          onUploadToProject={(files) => { void handleUpload(files); }}
          projectConversations={projectConversations}
          projects={projects}
          selectedConversation={selectedConversation}
          selectedProject={selectedProject}
          view={view}
        />
      </div>
    </div>
  );
}
