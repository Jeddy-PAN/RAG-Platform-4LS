"use client";

import type { DocumentItem, Project, UUID } from "@/lib/types";
import { ErrorState } from "./error-state";
import { ProjectList } from "./project-list";
import { SidebarUploadZone } from "./sidebar-upload-zone";

type ProjectSidebarProps = {
  projects: Project[];
  documentsByProject: Record<UUID, DocumentItem[]>;
  activeProjectId: UUID | null;
  expandedProjectIds: Set<UUID>;
  editMode: boolean;
  isLoadingProjects: boolean;
  isUploading: boolean;
  loadingDocuments: Set<UUID>;
  error: string | null;
  onCreateProject: () => void;
  onToggleEditMode: () => void;
  onSelectProject: (projectId: UUID) => void;
  onToggleExpand: (projectId: UUID) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  onUpload: (files: File[]) => void;
};

export function ProjectSidebar({
  projects,
  documentsByProject,
  activeProjectId,
  expandedProjectIds,
  editMode,
  isLoadingProjects,
  isUploading,
  loadingDocuments,
  error,
  onCreateProject,
  onToggleEditMode,
  onSelectProject,
  onToggleExpand,
  onRenameProject,
  onDeleteProject,
  onUpload
}: ProjectSidebarProps) {
  return (
    <aside className="project-sidebar">
      <section className="sidebar-top">
        <div className="sidebar-heading">
          <div>
            <span className="sidebar-label">Projects</span>
            <strong>{projects.length}</strong>
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
        {error ? <ErrorState message={error} /> : null}
        <ProjectList
          activeProjectId={activeProjectId}
          documentsByProject={documentsByProject}
          editMode={editMode}
          expandedProjectIds={expandedProjectIds}
          loading={isLoadingProjects}
          loadingDocuments={loadingDocuments}
          onDeleteProject={onDeleteProject}
          onRenameProject={onRenameProject}
          onSelectProject={onSelectProject}
          onToggleExpand={onToggleExpand}
          projects={projects}
        />
      </section>
      <SidebarUploadZone disabled={!activeProjectId} isUploading={isUploading} onUpload={onUpload} />
    </aside>
  );
}
