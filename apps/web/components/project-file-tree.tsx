import { formatBytes } from "@/lib/format";
import {
  buildDocumentListSummary,
  getDuplicateFilenameCounts,
  sortDocumentsForDisplay
} from "@/lib/document-list";
import type { DocumentItem, UUID } from "@/lib/types";
import { StatusBadge } from "./status-badge";

type ProjectFileTreeProps = {
  documents: DocumentItem[];
  isLoading: boolean;
  busyDocumentIds: Set<UUID>;
  editMode: boolean;
  onDeleteDocument: (document: DocumentItem) => void;
  onReindexDocument: (document: DocumentItem) => void;
};

export function ProjectFileTree({
  documents,
  isLoading,
  busyDocumentIds,
  editMode,
  onDeleteDocument,
  onReindexDocument
}: ProjectFileTreeProps) {
  if (isLoading) {
    return <div className="file-tree-hint">Loading files</div>;
  }

  if (documents.length === 0) {
    return <div className="file-tree-hint">No files in this project</div>;
  }

  const sortedDocuments = sortDocumentsForDisplay(documents);
  const duplicateFilenameCounts = getDuplicateFilenameCounts(documents);
  const summary = buildDocumentListSummary(documents);

  return (
    <>
      <div className="file-tree-summary">
        <span>
          {summary.uniqueCount === summary.totalCount
            ? `${summary.totalCount} files`
            : `${summary.uniqueCount} unique / ${summary.totalCount} files`}
        </span>
        <span>{summary.indexedCount} indexed</span>
        {summary.pendingCount > 0 ? <span>{summary.pendingCount} pending</span> : null}
        {summary.failedCount > 0 ? <span>{summary.failedCount} failed</span> : null}
        {summary.duplicateCount > 0 ? <span>{summary.duplicateCount} duplicates</span> : null}
      </div>
      <ul className="file-tree">
        {sortedDocuments.map((document) => {
          const duplicateCount = duplicateFilenameCounts.get(document.filename);
          return (
            <li className="file-row" key={document.id} title={document.error_message ?? document.filename}>
              <div className="file-main">
                <span className="file-name">{document.filename}</span>
                <span className="file-meta">
                  <StatusBadge status={document.status} />
                  <span>{formatBytes(document.file_size_bytes)}</span>
                  {duplicateCount ? <span className="duplicate-badge">x{duplicateCount}</span> : null}
                </span>
              </div>
              {editMode ? (
                <div className="file-actions">
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
              ) : null}
              {document.error_message ? <p className="file-error">{document.error_message}</p> : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}
