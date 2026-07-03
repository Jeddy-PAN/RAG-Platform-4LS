"use client";

import { useState } from "react";
import { metadataLabel } from "@/lib/format";
import type { ChatCitation } from "@/lib/types";

type CitationListProps = {
  citations: ChatCitation[];
};

export function CitationList({ citations }: CitationListProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (citations.length === 0) {
    return null;
  }

  return (
    <div className="citation-panel">
      <button
        aria-expanded={isExpanded}
        className="citation-toggle"
        onClick={() => setIsExpanded((current) => !current)}
        type="button"
      >
        <span>{isExpanded ? "Hide sources" : "Show sources"}</span>
        <strong>{citations.length}</strong>
      </button>
      {isExpanded ? (
        <ol className="citation-list">
          {citations.map((citation) => (
            <li key={`${citation.chunk_id}-${citation.citation_index}`}>
              <span>[{citation.citation_index}] {metadataLabel(citation.citation_metadata)}</span>
              {citation.quote ? <q>{citation.quote}</q> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
