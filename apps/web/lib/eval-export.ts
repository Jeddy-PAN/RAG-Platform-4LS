import type { EvalRun } from "@/lib/types";
import type { EvalRunCompare, EvalRunCompareCell } from "./eval-run-compare";

type CsvValue = string | number | boolean | null | undefined;

function csvCell(value: CsvValue) {
  if (value === null || value === undefined) {
    return "";
  }

  const text = String(value);
  if (!/[",\n\r]/.test(text)) {
    return text;
  }

  return `"${text.replaceAll('"', '""')}"`;
}

function metric(run: EvalRun, key: string) {
  const value = run.metrics[key];
  return typeof value === "number" ? value : null;
}

function cellOutcome(cell: EvalRunCompareCell) {
  if (!cell.resultId) {
    return "Missing";
  }
  if (cell.refused) {
    return "Refused";
  }
  return cell.answerMatched ? "Pass" : "Fail";
}

export function serializeCsv(rows: CsvValue[][]) {
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}

export function buildEvalRunJson(run: EvalRun) {
  return {
    run: {
      id: run.id,
      project_id: run.project_id,
      dataset_id: run.dataset_id,
      status: run.status,
      retrieval_mode: run.retrieval_mode,
      top_k: run.top_k,
      metrics: run.metrics,
      error_message: run.error_message,
      created_at: run.created_at,
      updated_at: run.updated_at
    },
    results: run.results.map((result) => ({
      id: result.id,
      question_id: result.question_id,
      question: result.question,
      answer: result.answer,
      score: result.score,
      hit: result.hit,
      citation_covered: result.citation_covered,
      answer_matched: result.answer_matched,
      refused: result.refused,
      retrieval_latency_ms: result.retrieval_latency_ms,
      generation_latency_ms: result.generation_latency_ms,
      result_metadata: result.result_metadata
    }))
  };
}

export function buildEvalRunCsv(run: EvalRun) {
  const rows: CsvValue[][] = [
    ["section", "run_id", "retrieval_mode", "top_k", "status", "created_at", "metric", "value"],
    ["run", run.id, run.retrieval_mode, run.top_k, run.status, run.created_at, "hit_rate", metric(run, "hit_rate")],
    [
      "run",
      run.id,
      run.retrieval_mode,
      run.top_k,
      run.status,
      run.created_at,
      "citation_coverage_rate",
      metric(run, "citation_coverage_rate")
    ],
    [
      "run",
      run.id,
      run.retrieval_mode,
      run.top_k,
      run.status,
      run.created_at,
      "answer_match_rate",
      metric(run, "answer_match_rate")
    ],
    [
      "run",
      run.id,
      run.retrieval_mode,
      run.top_k,
      run.status,
      run.created_at,
      "judge_match_rate",
      metric(run, "judge_match_rate")
    ],
    [
      "run",
      run.id,
      run.retrieval_mode,
      run.top_k,
      run.status,
      run.created_at,
      "avg_retrieval_latency_ms",
      metric(run, "avg_retrieval_latency_ms")
    ],
    [],
    [
      "question_id",
      "question",
      "answer",
      "score",
      "hit",
      "citation_covered",
      "answer_matched",
      "refused",
      "retrieval_latency_ms",
      "generation_latency_ms",
      "retrieval_log_id",
      "judge_enabled",
      "judge_passed",
      "judge_score",
      "judge_reason",
      "judge_error"
    ]
  ];

  for (const result of run.results) {
    rows.push([
      result.question_id,
      result.question,
      result.answer,
      result.score,
      result.hit,
      result.citation_covered,
      result.answer_matched,
      result.refused,
      result.retrieval_latency_ms,
      result.generation_latency_ms,
      result.result_metadata.retrieval_log_id,
      result.result_metadata.judge_enabled,
      result.result_metadata.judge_passed,
      result.result_metadata.judge_score,
      result.result_metadata.judge_reason,
      result.result_metadata.judge_error
    ]);
  }

  return serializeCsv(rows);
}

export function buildEvalCompareCsv(compare: EvalRunCompare) {
  const runIds = compare.runs.map((run) => run.id);
  const rows: CsvValue[][] = [
    ["section", "metric", ...runIds],
    ["metric", "Hit rate", ...compare.runs.map((run) => run.hitRate)],
    ["metric", "Citation", ...compare.runs.map((run) => run.citationCoverageRate)],
    ["metric", "Answer match", ...compare.runs.map((run) => run.answerMatchRate)],
    ["metric", "Judge", ...compare.runs.map((run) => run.judgeMatchRate)],
    ["metric", "Avg retrieval", ...compare.runs.map((run) => run.avgRetrievalLatencyMs)],
    ["metric", "Avg generation", ...compare.runs.map((run) => run.avgGenerationLatencyMs)],
    [],
    ["question_id", "question", ...runIds]
  ];

  for (const question of compare.questions) {
    rows.push([
      question.questionId,
      question.question,
      ...question.cells.map((cell) => cellOutcome(cell))
    ]);
    rows.push([
      `${question.questionId}:score`,
      "score",
      ...question.cells.map((cell) => cell.score)
    ]);
    rows.push([
      `${question.questionId}:hit`,
      "hit",
      ...question.cells.map((cell) => cell.hit)
    ]);
    rows.push([
      `${question.questionId}:citation`,
      "citation",
      ...question.cells.map((cell) => cell.citationCovered)
    ]);
  }

  return serializeCsv(rows);
}

export function buildExportFilename(prefix: string, id: string, extension: "csv" | "json") {
  const safePrefix = prefix.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const safeId = id.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  return `${safePrefix || "export"}-${safeId || "data"}.${extension}`;
}
