import type { EvalResult } from "@/lib/types";

export type EvalResultFilter =
  | "all"
  | "failed"
  | "judge_failed"
  | "retrieval_miss"
  | "citation_miss"
  | "refused";

export type EvalResultFilterOption = {
  id: EvalResultFilter;
  label: string;
  count: number;
};

const FILTER_LABELS: Record<EvalResultFilter, string> = {
  all: "All",
  failed: "Failed",
  judge_failed: "Judge failed",
  retrieval_miss: "Retrieval miss",
  citation_miss: "Citation miss",
  refused: "Refused"
};

function resultMatchesFilter(result: EvalResult, filter: EvalResultFilter) {
  switch (filter) {
    case "all":
      return true;
    case "failed":
      return result.score !== 1;
    case "judge_failed":
      return Boolean(
        result.result_metadata.judge_enabled &&
          (result.result_metadata.judge_passed === false ||
            result.result_metadata.judge_error)
      );
    case "retrieval_miss":
      return !result.hit;
    case "citation_miss":
      return !result.citation_covered;
    case "refused":
      return result.refused;
  }
}

export function filterEvalResults(results: EvalResult[], filter: EvalResultFilter) {
  return results.filter((result) => resultMatchesFilter(result, filter));
}

export function buildEvalResultFilterOptions(results: EvalResult[]): EvalResultFilterOption[] {
  const filters: EvalResultFilter[] = [
    "all",
    "failed",
    "judge_failed",
    "retrieval_miss",
    "citation_miss",
    "refused"
  ];

  return filters.map((filter) => ({
    id: filter,
    label: FILTER_LABELS[filter],
    count: filterEvalResults(results, filter).length
  }));
}
