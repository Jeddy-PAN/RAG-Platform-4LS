import type { Dispatch, SetStateAction } from "react";
import type { EvalResultFilter } from "@/lib/eval-result-filters";
import type { EvalRun, RetrievalLog, UUID } from "@/lib/types";
import { shortId } from "@/lib/format";
import { formatLatency, formatRate } from "./eval-helpers";

interface ResultFilterOption {
  id: EvalResultFilter;
  label: string;
  count: number;
}

interface EvalRunDetailProps {
  run: EvalRun;
  resultFilter: EvalResultFilter;
  setResultFilter: Dispatch<SetStateAction<EvalResultFilter>>;
  resultFilterOptions: ResultFilterOption[];
  filteredResults: EvalRun["results"];
  questionsById: Map<UUID, { question: string; expected_document_id?: string | null; expected_answer_notes?: string | null }>;
  documentNamesById: Map<UUID, string>;
  avgGenerationLatency: number | null;
  exportRunCsv: (run: EvalRun) => void;
  exportRunJson: (run: EvalRun) => void;
  isLoadingRetrievalLog: boolean;
  loadRetrievalLog: (logId: string) => Promise<void>;
  selectedRetrievalLog: RetrievalLog | null;
}

export function EvalRunDetail({
  run,
  resultFilter,
  setResultFilter,
  resultFilterOptions,
  filteredResults,
  questionsById,
  documentNamesById,
  avgGenerationLatency,
  exportRunCsv,
  exportRunJson,
  isLoadingRetrievalLog,
  loadRetrievalLog,
  selectedRetrievalLog,
}: EvalRunDetailProps) {
  return (
    <section className="retrieval-results">
      <div className="eval-run-toolbar">
        <div>
          <span className="sidebar-label">Run detail</span>
          <strong>
            {run.retrieval_mode} · top {run.top_k}
          </strong>
        </div>
        <div className="eval-export-actions">
          <button className="mini-button" onClick={() => exportRunCsv(run)} type="button">
            Export CSV
          </button>
          <button className="mini-button" onClick={() => exportRunJson(run)} type="button">
            Export JSON
          </button>
        </div>
      </div>
      <div className="eval-metrics">
        <div>
          <span>Hit rate</span>
          <strong>{formatRate(run.metrics.hit_rate)}</strong>
        </div>
        <div>
          <span>Citation</span>
          <strong>{formatRate(run.metrics.citation_coverage_rate)}</strong>
        </div>
        <div>
          <span>Answer match</span>
          <strong>{formatRate(run.metrics.answer_match_rate)}</strong>
        </div>
        <div>
          <span>Judge</span>
          <strong>{formatRate(run.metrics.judge_match_rate)}</strong>
        </div>
        <div>
          <span>Avg retrieval</span>
          <strong>{formatLatency(run.metrics.avg_retrieval_latency_ms)}</strong>
        </div>
        <div>
          <span>Avg generation</span>
          <strong>{formatLatency(avgGenerationLatency)}</strong>
        </div>
      </div>
      <div className="eval-result-filters">
        {resultFilterOptions.map((option) => (
          <button
            className={option.id === resultFilter ? "active" : ""}
            key={option.id}
            onClick={() => setResultFilter(option.id)}
            type="button"
          >
            <span>{option.label}</span>
            <strong>{option.count}</strong>
          </button>
        ))}
      </div>
      <ol>
        {filteredResults.length === 0 ? (
          <li>
            <p>No results match this filter.</p>
          </li>
        ) : (
          filteredResults.map((result) => {
            const expectedQuestion = questionsById.get(result.question_id);
            const expectedDocumentName = expectedQuestion?.expected_document_id
              ? documentNamesById.get(expectedQuestion.expected_document_id) ??
                expectedQuestion.expected_document_id
              : null;
            const retrievedCount = result.result_metadata.retrieved_chunk_ids?.length ?? 0;
            const citationCount = result.result_metadata.citation_chunk_ids?.length ?? 0;

            return (
              <li key={result.id}>
                <div className="result-heading">
                  <strong>{result.question}</strong>
                  <span>score {result.score ?? 0}</span>
                </div>
                <p>{result.answer ?? "No answer returned."}</p>
                <div className="score-row">
                  hit {String(result.hit)} · citation {String(result.citation_covered)} ·
                  answer {String(result.answer_matched)} · refused {String(result.refused)}
                  {expectedDocumentName ? ` · expected ${expectedDocumentName}` : ""}
                </div>
                <div className="score-row">
                  retrieval {formatLatency(result.retrieval_latency_ms)} · generation{" "}
                  {formatLatency(result.generation_latency_ms)} · retrieved {retrievedCount} ·
                  cited {citationCount}
                  {result.result_metadata.retrieval_log_id
                    ? ` · log ${shortId(result.result_metadata.retrieval_log_id)}`
                    : ""}
                </div>
                {result.result_metadata.retrieval_log_id ? (
                  <button
                    className="mini-button"
                    disabled={isLoadingRetrievalLog}
                    onClick={() => loadRetrievalLog(result.result_metadata.retrieval_log_id!)}
                    type="button"
                  >
                    {isLoadingRetrievalLog ? "Loading log" : "View retrieval log"}
                  </button>
                ) : null}
                {result.result_metadata.judge_enabled ? (
                  <div className="score-row">
                    judge {String(result.result_metadata.judge_passed ?? false)}
                    {typeof result.result_metadata.judge_score === "number"
                      ? ` · ${result.result_metadata.judge_score.toFixed(2)}`
                      : ""}
                    {result.result_metadata.judge_reason
                      ? ` · ${result.result_metadata.judge_reason}`
                      : ""}
                    {result.result_metadata.judge_error
                      ? ` · ${result.result_metadata.judge_error}`
                      : ""}
                  </div>
                ) : null}
              </li>
            );
          })
        )}
      </ol>
      {selectedRetrievalLog ? (
        <div className="retrieval-log-detail">
          <div className="result-heading">
            <strong>Retrieval log {shortId(selectedRetrievalLog.id)}</strong>
            <span>
              {selectedRetrievalLog.mode} · top {selectedRetrievalLog.top_k} ·{" "}
              {selectedRetrievalLog.latency_ms ?? 0}ms
            </span>
          </div>
          <p>{selectedRetrievalLog.query}</p>
          <ol>
            {selectedRetrievalLog.chunks.map((chunk) => (
              <li key={chunk.chunk_id}>
                <div className="result-heading">
                  <strong>
                    #{chunk.rank} {chunk.document_name}
                  </strong>
                  <span>chunk {chunk.chunk_index}</span>
                </div>
                <p>{chunk.text_preview}</p>
                <div className="score-row">
                  fused {chunk.fused_score?.toFixed(4) ?? "n/a"} · vector{" "}
                  {chunk.vector_score?.toFixed(4) ?? "n/a"} · keyword{" "}
                  {chunk.keyword_score?.toFixed(4) ?? "n/a"}
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
