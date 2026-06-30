import assert from "node:assert/strict";
import test from "node:test";
import { getNextExpandedProjectIds, openOnlyProject } from "./project-expansion.ts";

test("getNextExpandedProjectIds opens only the selected project", () => {
  assert.deepEqual([...getNextExpandedProjectIds(new Set(["project-a"]), "project-b")], ["project-b"]);
});

test("getNextExpandedProjectIds collapses the selected project when it is already open", () => {
  assert.deepEqual([...getNextExpandedProjectIds(new Set(["project-a"]), "project-a")], []);
});

test("openOnlyProject replaces any previous expanded project", () => {
  assert.deepEqual([...openOnlyProject("project-c")], ["project-c"]);
});
