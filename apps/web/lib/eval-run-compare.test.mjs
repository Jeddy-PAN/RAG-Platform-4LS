import assert from "node:assert/strict";
import test from "node:test";
import {
  buildEvalRunCompare,
  getRunGenerationAverage
} from "./eval-run-compare.ts";

function makeResult(overrides) {
  const generationLatencyMs = Object.hasOwn(overrides, "generation_latency_ms")
    ? overrides.generation_latency_ms
    : 100;

  return {
    id: overrides.id,
    question_id: overrides.question_id,
    question: overrides.question,
    answer: overrides.answer ?? "answer",
    hit: overrides.hit ?? true,
    citation_covered: overrides.citation_covered ?? true,
    refused: overrides.refused ?? false,
    answer_matched: overrides.answer_matched ?? true,
    retrieval_latency_ms: overrides.retrieval_latency_ms ?? 25,
    generation_latency_ms: generationLatencyMs,
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
    metrics: overrides.metrics,
    error_message: null,
    results: overrides.results,
    created_at: overrides.created_at,
    updated_at: overrides.updated_at
  };
}

const baselineRun = makeRun({
  id: "run-baseline",
  retrieval_mode: "hybrid",
  top_k: 8,
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-01T10:00:00Z",
  metrics: {
    hit_rate: 0.5,
    citation_coverage_rate: 0.5,
    answer_match_rate: 0.5,
    judge_match_rate: 0.5,
    avg_retrieval_latency_ms: 20
  },
  results: [
    makeResult({
      id: "baseline-q1",
      question_id: "q1",
      question: "Question one?",
      answer_matched: true,
      generation_latency_ms: 300
    }),
    makeResult({
      id: "baseline-q2",
      question_id: "q2",
      question: "Question two?",
      hit: false,
      citation_covered: false,
      answer_matched: false,
      score: 0,
      generation_latency_ms: 500
    })
  ]
});

const rerankRun = makeRun({
  id: "run-rerank",
  retrieval_mode: "hybrid",
  top_k: 12,
  created_at: "2026-06-01T11:00:00Z",
  updated_at: "2026-06-01T11:00:00Z",
  metrics: {
    hit_rate: 1,
    citation_coverage_rate: 1,
    answer_match_rate: 1,
    judge_match_rate: 1,
    avg_retrieval_latency_ms: 35
  },
  results: [
    makeResult({
      id: "rerank-q1",
      question_id: "q1",
      question: "Question one?",
      answer_matched: true,
      generation_latency_ms: 200
    }),
    makeResult({
      id: "rerank-q2",
      question_id: "q2",
      question: "Question two?",
      answer_matched: true,
      generation_latency_ms: null
    })
  ]
});

test("getRunGenerationAverage averages only numeric generation latencies", () => {
  assert.equal(getRunGenerationAverage(baselineRun), 400);
  assert.equal(getRunGenerationAverage(rerankRun), 200);
});

test("buildEvalRunCompare creates metric columns for selected runs", () => {
  const compare = buildEvalRunCompare([baselineRun, rerankRun]);

  assert.deepEqual(
    compare.runs.map((run) => ({
      id: run.id,
      label: run.label,
      answerMatchRate: run.answerMatchRate,
      avgGenerationLatencyMs: run.avgGenerationLatencyMs
    })),
    [
      {
        id: "run-baseline",
        label: "hybrid · top 8",
        answerMatchRate: 0.5,
        avgGenerationLatencyMs: 400
      },
      {
        id: "run-rerank",
        label: "hybrid · top 12",
        answerMatchRate: 1,
        avgGenerationLatencyMs: 200
      }
    ]
  );
});

test("buildEvalRunCompare aligns per-question outcomes across runs", () => {
  const compare = buildEvalRunCompare([baselineRun, rerankRun]);

  assert.deepEqual(
    compare.questions.map((question) => ({
      questionId: question.questionId,
      cells: question.cells.map((cell) => ({
        runId: cell.runId,
        hit: cell.hit,
        citationCovered: cell.citationCovered,
        answerMatched: cell.answerMatched,
        score: cell.score
      }))
    })),
    [
      {
        questionId: "q1",
        cells: [
          {
            runId: "run-baseline",
            hit: true,
            citationCovered: true,
            answerMatched: true,
            score: 1
          },
          {
            runId: "run-rerank",
            hit: true,
            citationCovered: true,
            answerMatched: true,
            score: 1
          }
        ]
      },
      {
        questionId: "q2",
        cells: [
          {
            runId: "run-baseline",
            hit: false,
            citationCovered: false,
            answerMatched: false,
            score: 0
          },
          {
            runId: "run-rerank",
            hit: true,
            citationCovered: true,
            answerMatched: true,
            score: 1
          }
        ]
      }
    ]
  );
});
