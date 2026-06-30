import assert from "node:assert/strict";
import test from "node:test";
import {
  buildEvalResultFilterOptions,
  filterEvalResults
} from "./eval-result-filters.ts";

const baseResult = {
  id: "result-ok",
  question_id: "question-ok",
  question: "What passed?",
  answer: "A grounded answer",
  hit: true,
  citation_covered: true,
  refused: false,
  answer_matched: true,
  retrieval_latency_ms: 40,
  generation_latency_ms: 300,
  score: 1,
  result_metadata: {
    retrieved_chunk_ids: ["chunk-a", "chunk-b"],
    citation_chunk_ids: ["chunk-a"]
  }
};

const results = [
  baseResult,
  {
    ...baseResult,
    id: "result-judge-failed",
    score: 0,
    result_metadata: {
      ...baseResult.result_metadata,
      judge_enabled: true,
      judge_passed: false
    }
  },
  {
    ...baseResult,
    id: "result-retrieval-miss",
    hit: false,
    score: 0
  },
  {
    ...baseResult,
    id: "result-citation-miss",
    citation_covered: false,
    score: 0.5
  },
  {
    ...baseResult,
    id: "result-refused",
    answer: null,
    refused: true,
    answer_matched: false,
    score: 0
  }
];

test("buildEvalResultFilterOptions counts actionable eval result groups", () => {
  const options = buildEvalResultFilterOptions(results);

  assert.deepEqual(
    options.map((option) => [option.id, option.count]),
    [
      ["all", 5],
      ["failed", 4],
      ["judge_failed", 1],
      ["retrieval_miss", 1],
      ["citation_miss", 1],
      ["refused", 1]
    ]
  );
});

test("filterEvalResults returns only matching eval results", () => {
  assert.deepEqual(
    filterEvalResults(results, "judge_failed").map((result) => result.id),
    ["result-judge-failed"]
  );
  assert.deepEqual(
    filterEvalResults(results, "failed").map((result) => result.id),
    [
      "result-judge-failed",
      "result-retrieval-miss",
      "result-citation-miss",
      "result-refused"
    ]
  );
  assert.deepEqual(
    filterEvalResults(results, "all").map((result) => result.id),
    results.map((result) => result.id)
  );
});
