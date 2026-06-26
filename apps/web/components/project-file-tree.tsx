import { formatBytes } from "@/lib/format";
import type { DocumentItem, UUID } from "@/lib/types";
import { StatusBadge } from "./status-badge";

type ProjectFileTreeProps = {
  documents: DocumentItem[];
  isLoading: boolean;
  busyDocumentIds: Set<UUID>;
  onDeleteDocument: (document: DocumentItem) => void;
  onRefreshDocuments: () => void;
  onReindexDocument: (document: DocumentItem) => void;
};

export function ProjectFileTree({
  documents,
  isLoading,
  busyDocumentIds,
  onDeleteDocument,
  onRefreshDocuments,
  onReindexDocument
}: ProjectFileTreeProps) {
  if (isLoading) {
    return <div className="file-tree-hint">Loading files</div>;
  }

  if (documents.length === 0) {
    return <div className="file-tree-hint">No files in this project</div>;
  }

  return (
    <ul className="file-tree">
      {documents.map((document) => (
        <li className="file-row" key={document.id} title={document.error_message ?? document.filename}>
          <div className="file-main">
            <span className="file-name">{document.filename}</span>
            <span className="file-meta">
              <StatusBadge status={document.status} />
              <span>{formatBytes(document.file_size_bytes)}</span>
            </span>
          </div>
          <div className="file-actions">
            <button
              aria-label={`Refresh ${document.filename}`}
              className="mini-button"
              onClick={onRefreshDocuments}
              type="button"
            >
              Refresh
            </button>
            <button
              aria-label={`Reindex ${document.filename}`}
              className="mini-button"
              disabled={busyDocumentIds.has(document.id)}
              onClick={() => onReindexDocument(document)}
              type="button"
            >
              Reindex
            </button>
            <button
              aria-label={`Delete ${document.filename}`}
              className="mini-button danger"
              disabled={busyDocumentIds.has(document.id)}
              onClick={() => onDeleteDocument(document)}
              type="button"
            >
              Delete
            </button>
          </div>
          {document.error_message ? <p className="file-error">{document.error_message}</p> : null}
        </li>
      ))}
    </ul>
  );
}
