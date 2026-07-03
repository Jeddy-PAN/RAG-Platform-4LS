import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDocumentListSummary,
  getDuplicateFilenameCounts,
  sortDocumentsForDisplay
} from "./document-list.ts";

function makeDocument(filename, status = "indexed") {
  return {
    id: `${filename}-${Math.random()}`,
    project_id: "project-a",
    filename,
    content_type: "text/markdown",
    storage_path: `/tmp/${filename}`,
    file_size_bytes: 100,
    status,
    error_message: null,
    created_at: "2026-07-03T00:00:00Z",
    updated_at: "2026-07-03T00:00:00Z"
  };
}

test("sortDocumentsForDisplay orders numbered filenames naturally", () => {
  const documents = [
    makeDocument("10-outbox.md"),
    makeDocument("02-ledger.md"),
    makeDocument("01-overview.md")
  ];

  assert.deepEqual(
    sortDocumentsForDisplay(documents).map((document) => document.filename),
    ["01-overview.md", "02-ledger.md", "10-outbox.md"]
  );
});

test("getDuplicateFilenameCounts counts repeated filenames", () => {
  const documents = [
    makeDocument("01-overview.md"),
    makeDocument("01-overview.md"),
    makeDocument("02-ledger.md")
  ];

  assert.deepEqual([...getDuplicateFilenameCounts(documents).entries()], [["01-overview.md", 2]]);
});

test("buildDocumentListSummary reports total, unique, indexed, and duplicate counts", () => {
  const documents = [
    makeDocument("01-overview.md", "indexed"),
    makeDocument("01-overview.md", "indexed"),
    makeDocument("02-ledger.md", "processing"),
    makeDocument("03-risk.md", "failed")
  ];

  assert.deepEqual(buildDocumentListSummary(documents), {
    totalCount: 4,
    uniqueCount: 3,
    indexedCount: 2,
    duplicateCount: 1,
    failedCount: 1,
    pendingCount: 1
  });
});
