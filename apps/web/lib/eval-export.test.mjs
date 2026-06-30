import assert from "node:assert/strict";
import test from "node:test";
import { buildEvalRunCompare } from "./eval-run-compare.ts";
import {
  buildEvalCompareCsv,
  buildEvalRunCsv,
  buildEvalRunJson,
  buildExportFilename,
  serializeCsv
} from "./eval-export.ts";

function makeResult(overrides) {
  return {
    id: overrides.id,
    question_id: overrides.question_id,
    question: overrides.question,
    answer: overrides.answer ?? "answer",
    hit: overrides.hit ?? true,
    citation_covered: overrides.citation_covered ?? true,
    refused: overrides.refused ?? false,
    answer_matched: overrides.answer_matched ?? true,
    retrieval_latency_ms: overrides.retrieval_latency_ms ?? 20,
    generation_latency_ms: overrides.generation_latency_ms ?? 100,
    score: overrides.score ?? 1,
    result_metadata: overrides.result_metadata ?? {}
  };
}

function makeRun(overrides) {
  return {
    id: overrides.id,
    project_id: "project-1",
    dataset_id: "dataset-1",
    status: "completed",
    retrieval_mode: overrides.retrieval_mode ?? "hybrid",
    top_k: overrides.top_k ?? 8,
    metrics: overrides.metrics ?? {
      hit_rate: 1,
      citation_coverage_rate: 1,
      answer_match_rate: 1,
      judge_match_rate: 1,
      avg_retrieval_latency_ms: 20
    },
    error_message: null,
    results: overrides.results,
    created_at: overrides.created_at ?? "2026-06-01T10:00:00Z",
    updated_at: overrides.updated_at ?? "2026-06-01T10:00:00Z"
  };
}

const baselineRun = makeRun({
  id: "run-baseline",
  top_k: 8,
  results: [
    makeResult({
      id: "result-1",
      question_id: "q1",
      question: "What, exactly?",
      answer: "Answer with comma, newline\nand quote \"inside\".",
      result_metadata: {
        retrieval_log_id: "log-1",
        judge_enabled: true,
        judge_passed: true,
        judge_score: 0.95,
        judge_reason: "grounded"
      }
    }),
    makeResult({
      id: "result-2",
      question_id: "q2",
      question: "What failed?",
      answer_matched: false,
      citation_covered: false,
      score: 0.25
    })
  ]
});

const improvedRun = makeRun({
  id: "run-improved",
  top_k: 12,
  created_at: "2026-06-01T11:00:00Z",
  results: [
    makeResult({
      id: "result-3",
      question_id: "q1",
      question: "What, exactly?"
    }),
    makeResult({
      id: "result-4",
      question_id: "q2",
      question: "What failed?",
      answer_matched: true,
      citation_covered: true,
      score: 1
    })
  ]
});

test("serializeCsv escapes commas, quotes, and newlines", () => {
  assert.equal(
    serializeCsv([
      ["plain", "with,comma", "with \"quote\"", "with\nnewline"],
      ["next", null, true, 1]
    ]),
    'plain,"with,comma","with ""quote""","with\nnewline"\nnext,,true,1'
  );
});

test("buildEvalRunCsv exports run-level and per-result rows", () => {
  const csv = buildEvalRunCsv(baselineRun);

  assert.match(csv, /section,run_id,retrieval_mode,top_k,status,created_at,metric,value/);
  assert.match(csv, /run,run-baseline,hybrid,8,completed,2026-06-01T10:00:00Z,hit_rate,1/);
  assert.match(csv, /question_id,question,answer,score,hit,citation_covered,answer_matched,refused/);
  assert.match(csv, /q1,"What, exactly\?","Answer with comma, newline\nand quote ""inside""\.",1,true,true,true,false/);
});

test("buildEvalRunJson keeps run metadata and result rows in a stable object", () => {
  const payload = buildEvalRunJson(baselineRun);

  assert.deepEqual(payload.run, {
    id: "run-baseline",
    project_id: "project-1",
    dataset_id: "dataset-1",
    status: "completed",
    retrieval_mode: "hybrid",
    top_k: 8,
    metrics: baselineRun.metrics,
    error_message: null,
    created_at: "2026-06-01T10:00:00Z",
    updated_at: "2026-06-01T10:00:00Z"
  });
  assert.equal(payload.results.length, 2);
  assert.equal(payload.results[0].result_metadata.judge_score, 0.95);
});

test("buildEvalCompareCsv exports metrics and question matrix sections", () => {
  const compare = buildEvalRunCompare([baselineRun, improvedRun]);
  const csv = buildEvalCompareCsv(compare);

  assert.match(csv, /section,metric,run-baseline,run-improved/);
  assert.match(csv, /metric,Answer match,1,1/);
  assert.match(csv, /question_id,question,run-baseline,run-improved/);
  assert.match(csv, /q2,What failed\?,Fail,Pass/);
});

test("buildExportFilename creates stable lightweight filenames", () => {
  assert.equal(
    buildExportFilename("eval run", "run-baseline", "csv"),
    "eval-run-run-baseline.csv"
  );
});
