import { formatBytes } from "@/lib/format";
import type { DocumentItem } from "@/lib/types";
import { StatusBadge } from "./status-badge";

type ProjectFileTreeProps = {
  documents: DocumentItem[];
  isLoading: boolean;
};

export function ProjectFileTree({ documents, isLoading }: ProjectFileTreeProps) {
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
          <span className="file-name">{document.filename}</span>
          <span className="file-meta">
            <StatusBadge status={document.status} />
            <span>{formatBytes(document.file_size_bytes)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
