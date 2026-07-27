import type { UUID } from "@/lib/types";
import type { EvalRunCompareCell } from "@/lib/eval-run-compare";
import { formatCellOutcome, formatDateTime, getCellClassName } from "./eval-helpers";

interface CompareRunEntry {
  id: string;
  label: string;
  createdAt: string;
  resultCount: number;
}

interface CompareQuestion {
  questionId: string;
  question: string;
  cells: EvalRunCompareCell[];
}

interface CompareData {
  runs: CompareRunEntry[];
  questions: CompareQuestion[];
}

interface CompareMetricRow {
  label: string;
  values: string[];
}

interface EvalComparePanelProps {
  compare: CompareData;
  compareMetricRows: CompareMetricRow[];
  loadedCount: number;
  totalCount: number;
  exportCompareCsv: () => void;
  resetCompareState: () => void;
}

export function EvalComparePanel({
  compare,
  compareMetricRows,
  loadedCount,
  totalCount,
  exportCompareCsv,
  resetCompareState,
}: EvalComparePanelProps) {
  if (totalCount === 0) return null;

  return (
    <section className="eval-compare-panel">
      <div className="eval-compare-heading">
        <div>
          <span className="sidebar-label">Run compare</span>
          <strong>
            {loadedCount}/{totalCount} loaded
          </strong>
        </div>
        <div className="eval-export-actions">
          <button
            className="mini-button"
            disabled={compare.runs.length < 2}
            onClick={exportCompareCsv}
            type="button"
          >
            Export CSV
          </button>
          <button className="mini-button" onClick={resetCompareState} type="button">
            Clear
          </button>
        </div>
      </div>
      {compare.runs.length < 2 ? (
        <p className="sidebar-empty">Select at least 2 runs to compare metrics and questions.</p>
      ) : (
        <>
          <div className="eval-compare-scroll">
            <table className="eval-compare-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  {compare.runs.map((item) => (
                    <th key={item.id}>
                      <span>{item.label}</span>
                      <small>
                        {formatDateTime(item.createdAt)} · {item.resultCount} results
                      </small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compareMetricRows.map((row) => (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    {row.values.map((value, index) => (
                      <td key={`${row.label}-${compare.runs[index]?.id ?? index}`}>
                        {value}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="eval-compare-scroll">
            <table className="eval-compare-table question-matrix">
              <thead>
                <tr>
                  <th>Question</th>
                  {compare.runs.map((item) => (
                    <th key={item.id}>{item.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compare.questions.map((questionItem) => (
                  <tr key={questionItem.questionId}>
                    <td>{questionItem.question}</td>
                    {questionItem.cells.map((cell) => (
                      <td key={`${questionItem.questionId}-${cell.runId}`}>
                        <span className={getCellClassName(cell)}>
                          {formatCellOutcome(cell)}
                        </span>
                        <small>
                          score {cell.score ?? "n/a"} · hit {String(cell.hit ?? false)} ·
                          citation {String(cell.citationCovered ?? false)}
                        </small>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
