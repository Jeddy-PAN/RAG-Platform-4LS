import assert from "node:assert/strict";
import test from "node:test";
import { getAutosizeTextareaHeight } from "./textarea-autosize.ts";

test("getAutosizeTextareaHeight clamps scroll height within composer bounds", () => {
  assert.equal(getAutosizeTextareaHeight(12), "48px");
  assert.equal(getAutosizeTextareaHeight(96), "96px");
  assert.equal(getAutosizeTextareaHeight(220), "144px");
});

test("getAutosizeTextareaHeight accepts custom bounds", () => {
  assert.equal(getAutosizeTextareaHeight(20, 32, 80), "32px");
  assert.equal(getAutosizeTextareaHeight(72, 32, 80), "72px");
  assert.equal(getAutosizeTextareaHeight(120, 32, 80), "80px");
});
