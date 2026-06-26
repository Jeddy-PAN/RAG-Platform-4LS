import type { DocumentItem, Project, UUID } from "@/lib/types";
import { LoadingState } from "./loading-state";
import { ProjectRow } from "./project-row";

type ProjectListProps = {
  projects: Project[];
  documentsByProject: Record<UUID, DocumentItem[]>;
  activeProjectId: UUID | null;
  busyDocumentIds: Set<UUID>;
  expandedProjectIds: Set<UUID>;
  editMode: boolean;
  loading: boolean;
  loadingDocuments: Set<UUID>;
  onDeleteDocument: (projectId: UUID, document: DocumentItem) => void;
  onRefreshDocuments: (projectId: UUID) => void;
  onReindexDocument: (projectId: UUID, document: DocumentItem) => void;
  onSelectProject: (projectId: UUID) => void;
  onToggleExpand: (projectId: UUID) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
};

export function ProjectList({
  projects,
  documentsByProject,
  activeProjectId,
  busyDocumentIds,
  expandedProjectIds,
  editMode,
  loading,
  loadingDocuments,
  onDeleteDocument,
  onRefreshDocuments,
  onReindexDocument,
  onSelectProject,
  onToggleExpand,
  onRenameProject,
  onDeleteProject
}: ProjectListProps) {
  if (loading) {
    return <LoadingState label="Loading projects" />;
  }

  if (projects.length === 0) {
    return <p className="sidebar-empty">Create a project to start a local knowledge base.</p>;
  }

  return (
    <ul className="project-list">
      {projects.map((project) => (
        <ProjectRow
          activeProjectId={activeProjectId}
          busyDocumentIds={busyDocumentIds}
          documents={documentsByProject[project.id] ?? []}
          editMode={editMode}
          expanded={expandedProjectIds.has(project.id)}
          key={project.id}
          loadingFiles={loadingDocuments.has(project.id)}
          onDelete={onDeleteProject}
          onDeleteDocument={onDeleteDocument}
          onRefreshDocuments={onRefreshDocuments}
          onReindexDocument={onReindexDocument}
          onRename={onRenameProject}
          onSelect={onSelectProject}
          onToggleExpand={onToggleExpand}
          project={project}
        />
      ))}
    </ul>
  );
}
