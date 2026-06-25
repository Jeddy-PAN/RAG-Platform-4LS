import { formatLatency, shortId } from "@/lib/format";
import type { RetrievalResponse } from "@/lib/types";

type RetrievalResultsProps = {
  response: RetrievalResponse | null;
};

export function RetrievalResults({ response }: RetrievalResultsProps) {
  if (!response) {
    return <p className="retrieval-empty">Run a query to inspect ranked chunks and scores.</p>;
  }

  return (
    <section className="retrieval-results">
      <div className="retrieval-summary">
        <span>{response.mode}</span>
        <span>{response.results.length} results</span>
        <span>{formatLatency(response.latency_ms)}</span>
        <span>log {shortId(response.retrieval_log_id)}</span>
      </div>
      <ol>
        {response.results.map((result) => (
          <li key={result.chunk_id}>
            <div className="result-heading">
              <strong>#{result.rank} {result.document_name}</strong>
              <span>chunk {result.chunk_index}</span>
            </div>
            <p>{result.text_preview}</p>
            <div className="score-row">
              <span>fused {result.fused_score?.toFixed(4) ?? "n/a"}</span>
              <span>vector {result.vector_score?.toFixed(4) ?? "n/a"}</span>
              <span>keyword {result.keyword_score?.toFixed(4) ?? "n/a"}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
