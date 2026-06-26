import type { DocumentItem, Project, UUID } from "@/lib/types";
import { ProjectFileTree } from "./project-file-tree";

type ProjectRowProps = {
  project: Project;
  documents: DocumentItem[];
  activeProjectId: UUID | null;
  busyDocumentIds: Set<UUID>;
  expanded: boolean;
  editMode: boolean;
  loadingFiles: boolean;
  onDeleteDocument: (projectId: UUID, document: DocumentItem) => void;
  onReindexDocument: (projectId: UUID, document: DocumentItem) => void;
  onSelect: (projectId: UUID) => void;
  onToggleExpand: (projectId: UUID) => void;
  onRename: (project: Project) => void;
  onDelete: (project: Project) => void;
};

export function ProjectRow({
  project,
  documents,
  activeProjectId,
  busyDocumentIds,
  expanded,
  editMode,
  loadingFiles,
  onDeleteDocument,
  onReindexDocument,
  onSelect,
  onToggleExpand,
  onRename,
  onDelete
}: ProjectRowProps) {
  const isActive = activeProjectId === project.id;

  return (
    <li className="project-item">
      <div className={`project-row ${isActive ? "selected" : ""}`}>
        <button
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse project files" : "Expand project files"}
          className="icon-button disclosure"
          onClick={() => onToggleExpand(project.id)}
          type="button"
        >
          {expanded ? "v" : ">"}
        </button>
        <button
          className="project-select"
          onClick={() => onSelect(project.id)}
          onDoubleClick={() => onSelect(project.id)}
          title="Click or double-click to select project"
          type="button"
        >
          <span>{project.name}</span>
          {project.description ? <small>{project.description}</small> : null}
        </button>
        {editMode ? (
          <div className="project-actions">
            <button className="text-button" onClick={() => onRename(project)} type="button">
              Edit
            </button>
            <button className="text-button danger" onClick={() => onDelete(project)} type="button">
              Delete
            </button>
          </div>
        ) : null}
      </div>
      {expanded ? (
        <ProjectFileTree
          busyDocumentIds={busyDocumentIds}
          documents={documents}
          editMode={editMode}
          isLoading={loadingFiles}
          onDeleteDocument={(document) => onDeleteDocument(project.id, document)}
          onReindexDocument={(document) => onReindexDocument(project.id, document)}
        />
      ) : null}
    </li>
  );
}
