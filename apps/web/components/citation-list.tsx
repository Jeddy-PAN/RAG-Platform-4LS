import { metadataLabel } from "@/lib/format";
import type { ChatCitation } from "@/lib/types";

type CitationListProps = {
  citations: ChatCitation[];
};

export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <ol className="citation-list">
      {citations.map((citation) => (
        <li key={`${citation.chunk_id}-${citation.citation_index}`}>
          <span>[{citation.citation_index}] {metadataLabel(citation.citation_metadata)}</span>
          {citation.quote ? <q>{citation.quote}</q> : null}
        </li>
      ))}
    </ol>
  );
}
