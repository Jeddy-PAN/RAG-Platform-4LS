import type { DocumentItem } from "./types";

export type DocumentListSummary = {
  totalCount: number;
  uniqueCount: number;
  indexedCount: number;
  duplicateCount: number;
  failedCount: number;
  pendingCount: number;
};

const filenameCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base"
});

export function sortDocumentsForDisplay(documents: DocumentItem[]) {
  return [...documents].sort((left, right) => {
    const filenameOrder = filenameCollator.compare(left.filename, right.filename);
    if (filenameOrder !== 0) {
      return filenameOrder;
    }
    return left.created_at.localeCompare(right.created_at);
  });
}

export function getDuplicateFilenameCounts(documents: DocumentItem[]) {
  const counts = new Map<string, number>();
  for (const document of documents) {
    counts.set(document.filename, (counts.get(document.filename) ?? 0) + 1);
  }

  for (const [filename, count] of counts) {
    if (count < 2) {
      counts.delete(filename);
    }
  }

  return counts;
}

export function buildDocumentListSummary(documents: DocumentItem[]): DocumentListSummary {
  const duplicateCounts = getDuplicateFilenameCounts(documents);
  return {
    totalCount: documents.length,
    uniqueCount: new Set(documents.map((document) => document.filename)).size,
    indexedCount: documents.filter((document) => document.status === "indexed").length,
    duplicateCount: [...duplicateCounts.values()].reduce((total, count) => total + count - 1, 0),
    failedCount: documents.filter((document) => document.status === "failed").length,
    pendingCount: documents.filter(
      (document) => document.status === "uploaded" || document.status === "processing"
    ).length
  };
}
