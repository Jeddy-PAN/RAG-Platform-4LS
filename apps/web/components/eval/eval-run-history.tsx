import type { EvalRun, EvalRunSummary, UUID } from "@/lib/types";
import { formatRate } from "./eval-helpers";

interface EvalRunHistoryProps {
  runs: EvalRunSummary[];
  selectedRun: EvalRun | null;
  compareRunIds: UUID[];
  loadingCompareRunIds: Set<UUID>;
  isLoadingRun: boolean;
  loadRunDetail: (runId: UUID) => Promise<void>;
  toggleCompareRun: (runId: UUID) => void;
}

export function EvalRunHistory({
  runs,
  selectedRun,
  compareRunIds,
  loadingCompareRunIds,
  isLoadingRun,
  loadRunDetail,
  toggleCompareRun,
}: EvalRunHistoryProps) {
  if (runs.length === 0) {
    return <p className="sidebar-empty">No runs for this dataset.</p>;
  }

  return (
    <div className="eval-run-list compact">
      {runs.map((item) => {
        const isCompareSelected = compareRunIds.includes(item.id);
        const isCompareDisabled = !isCompareSelected && compareRunIds.length >= 4;
        const isCompareLoading = loadingCompareRunIds.has(item.id);

        return (
          <div
            className={selectedRun?.id === item.id ? "eval-run-row active" : "eval-run-row"}
            key={item.id}
          >
            <button
              className="eval-run-open"
              disabled={isLoadingRun}
              onClick={() => loadRunDetail(item.id)}
              type="button"
            >
              <span>
                {item.retrieval_mode} · top {item.top_k}
              </span>
              <strong>{formatRate(item.metrics.answer_match_rate)}</strong>
              <small>
                {item.status} · {item.result_count} results
              </small>
            </button>
            <button
              aria-label={`${isCompareSelected ? "Remove from" : "Add to"} compare`}
              className={isCompareSelected ? "mini-button active" : "mini-button"}
              disabled={isCompareDisabled || isCompareLoading}
              onClick={() => toggleCompareRun(item.id)}
              type="button"
            >
              {isCompareLoading ? "..." : isCompareSelected ? "Added" : "+"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
