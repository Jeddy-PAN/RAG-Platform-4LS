import type { EvalResult, EvalRun, UUID } from "@/lib/types";

export type EvalRunCompareRun = {
  id: UUID;
  label: string;
  createdAt: string;
  status: EvalRun["status"];
  hitRate: number | undefined;
  citationCoverageRate: number | undefined;
  answerMatchRate: number | undefined;
  judgeMatchRate: number | undefined;
  avgRetrievalLatencyMs: number | undefined;
  avgGenerationLatencyMs: number | null;
  resultCount: number;
};

export type EvalRunCompareCell = {
  runId: UUID;
  resultId: UUID | null;
  hit: boolean | null;
  citationCovered: boolean | null;
  answerMatched: boolean | null;
  refused: boolean | null;
  judgePassed: boolean | null;
  score: number | null;
};

export type EvalRunCompareQuestion = {
  questionId: UUID;
  question: string;
  cells: EvalRunCompareCell[];
};

export type EvalRunCompare = {
  runs: EvalRunCompareRun[];
  questions: EvalRunCompareQuestion[];
};

export function getRunGenerationAverage(run: EvalRun): number | null {
  const latencies = run.results
    .map((result) => result.generation_latency_ms)
    .filter((value): value is number => typeof value === "number");

  if (latencies.length === 0) {
    return null;
  }

  return latencies.reduce((total, value) => total + value, 0) / latencies.length;
}

function getMetric(run: EvalRun, key: string): number | undefined {
  const value = run.metrics[key];
  return typeof value === "number" ? value : undefined;
}

function buildRunLabel(run: EvalRun): string {
  return `${run.retrieval_mode} · top ${run.top_k}`;
}

function buildCell(runId: UUID, result: EvalResult | undefined): EvalRunCompareCell {
  if (!result) {
    return {
      runId,
      resultId: null,
      hit: null,
      citationCovered: null,
      answerMatched: null,
      refused: null,
      judgePassed: null,
      score: null
    };
  }

  return {
    runId,
    resultId: result.id,
    hit: result.hit,
    citationCovered: result.citation_covered,
    answerMatched: result.answer_matched,
    refused: result.refused,
    judgePassed:
      typeof result.result_metadata.judge_passed === "boolean"
        ? result.result_metadata.judge_passed
        : null,
    score: result.score
  };
}

export function buildEvalRunCompare(runs: EvalRun[]): EvalRunCompare {
  const questionOrder: UUID[] = [];
  const questionTextById = new Map<UUID, string>();

  for (const run of runs) {
    for (const result of run.results) {
      if (!questionTextById.has(result.question_id)) {
        questionOrder.push(result.question_id);
        questionTextById.set(result.question_id, result.question);
      }
    }
  }

  const resultsByRunAndQuestion = new Map<UUID, Map<UUID, EvalResult>>();

  for (const run of runs) {
    resultsByRunAndQuestion.set(
      run.id,
      new Map(run.results.map((result) => [result.question_id, result]))
    );
  }

  return {
    runs: runs.map((run) => ({
      id: run.id,
      label: buildRunLabel(run),
      createdAt: run.created_at,
      status: run.status,
      hitRate: getMetric(run, "hit_rate"),
      citationCoverageRate: getMetric(run, "citation_coverage_rate"),
      answerMatchRate: getMetric(run, "answer_match_rate"),
      judgeMatchRate: getMetric(run, "judge_match_rate"),
      avgRetrievalLatencyMs: getMetric(run, "avg_retrieval_latency_ms"),
      avgGenerationLatencyMs: getRunGenerationAverage(run),
      resultCount: run.results.length
    })),
    questions: questionOrder.map((questionId) => ({
      questionId,
      question: questionTextById.get(questionId) ?? questionId,
      cells: runs.map((run) => buildCell(run.id, resultsByRunAndQuestion.get(run.id)?.get(questionId)))
    }))
  };
}
