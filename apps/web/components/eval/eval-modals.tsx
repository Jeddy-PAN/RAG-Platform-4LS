import type { Dispatch, SetStateAction } from "react";
import type { DocumentItem, EvalDataset, RetrievalMode, UUID } from "@/lib/types";

export type EvalModalType = "dataset" | "question" | "run" | null;

interface EvalModalsProps {
  modal: EvalModalType;
  onClose: () => void;
  // dataset
  datasetName: string;
  setDatasetName: Dispatch<SetStateAction<string>>;
  createDataset: () => Promise<void>;
  // question
  question: string;
  setQuestion: Dispatch<SetStateAction<string>>;
  expectedNotes: string;
  setExpectedNotes: Dispatch<SetStateAction<string>>;
  expectedDocumentId: string;
  setExpectedDocumentId: Dispatch<SetStateAction<string>>;
  expectedChunkId: string;
  setExpectedChunkId: Dispatch<SetStateAction<string>>;
  addQuestion: () => Promise<void>;
  documents: DocumentItem[];
  selectedDatasetId: UUID | "";
  // run
  mode: RetrievalMode;
  setMode: Dispatch<SetStateAction<RetrievalMode>>;
  topK: number;
  setTopK: Dispatch<SetStateAction<number>>;
  rerankerEnabled: boolean;
  setRerankerEnabled: Dispatch<SetStateAction<boolean>>;
  rerankerCandidateLimit: number;
  setRerankerCandidateLimit: Dispatch<SetStateAction<number>>;
  judgeEnabled: boolean;
  setJudgeEnabled: Dispatch<SetStateAction<boolean>>;
  runEval: () => Promise<void>;
  isRunning: boolean;
  selectedDataset: EvalDataset | null;
}

export function EvalModals({
  modal,
  onClose,
  datasetName,
  setDatasetName,
  createDataset,
  question,
  setQuestion,
  expectedNotes,
  setExpectedNotes,
  expectedDocumentId,
  setExpectedDocumentId,
  expectedChunkId,
  setExpectedChunkId,
  addQuestion,
  documents,
  selectedDatasetId,
  mode,
  setMode,
  topK,
  setTopK,
  rerankerEnabled,
  setRerankerEnabled,
  rerankerCandidateLimit,
  setRerankerCandidateLimit,
  judgeEnabled,
  setJudgeEnabled,
  runEval,
  isRunning,
  selectedDataset,
}: EvalModalsProps) {
  if (!modal) return null;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-modal="true"
        className="tool-modal"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="modal-heading">
          <div>
            <span className="sidebar-label">Eval</span>
            <strong>
              {modal === "dataset"
                ? "New dataset"
                : modal === "question"
                  ? "Add question"
                  : "Run settings"}
            </strong>
          </div>
          <button className="icon-button" onClick={onClose} type="button">
            Close
          </button>
        </div>

        {modal === "dataset" ? (
          <>
            <label>
              Dataset name
              <input
                onChange={(event) => setDatasetName(event.target.value)}
                placeholder="Quantum basics"
                type="text"
                value={datasetName}
              />
            </label>
            <button disabled={!datasetName.trim()} onClick={createDataset} type="button">
              Create dataset
            </button>
          </>
        ) : null}

        {modal === "question" ? (
          <>
            <label>
              Question
              <textarea
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Question expected from this knowledge base"
                rows={4}
                value={question}
              />
            </label>
            <label>
              Expected answer notes
              <input
                onChange={(event) => setExpectedNotes(event.target.value)}
                placeholder="keywords such as quantum supremacy"
                type="text"
                value={expectedNotes}
              />
            </label>
            <label>
              Expected document
              <select
                onChange={(event) => setExpectedDocumentId(event.target.value)}
                value={expectedDocumentId}
              >
                <option value="">Any retrieved document</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.filename} · {document.status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Expected chunk id
              <input
                onChange={(event) => setExpectedChunkId(event.target.value)}
                placeholder="optional"
                type="text"
                value={expectedChunkId}
              />
            </label>
            <button
              disabled={!selectedDatasetId || !question.trim()}
              onClick={addQuestion}
              type="button"
            >
              Add question
            </button>
          </>
        ) : null}

        {modal === "run" ? (
          <>
            <label>
              Mode
              <select onChange={(event) => setMode(event.target.value as RetrievalMode)} value={mode}>
                <option value="hybrid">Hybrid</option>
                <option value="vector">Vector</option>
                <option value="keyword">Keyword</option>
              </select>
            </label>
            <label>
              Top K
              <input
                min={1}
                max={50}
                onChange={(event) => setTopK(Number(event.target.value))}
                type="number"
                value={topK}
              />
            </label>
            <label className="checkbox-label">
              <input
                checked={rerankerEnabled}
                onChange={(event) => setRerankerEnabled(event.target.checked)}
                type="checkbox"
              />
              Reranker
            </label>
            <label>
              Rerank candidates
              <input
                disabled={!rerankerEnabled}
                max={200}
                min={1}
                onChange={(event) => setRerankerCandidateLimit(Number(event.target.value))}
                type="number"
                value={rerankerCandidateLimit}
              />
            </label>
            <label className="checkbox-label">
              <input
                checked={judgeEnabled}
                onChange={(event) => setJudgeEnabled(event.target.checked)}
                type="checkbox"
              />
              LLM judge
            </label>
            <button
              disabled={!selectedDatasetId || isRunning || !selectedDataset?.question_count}
              onClick={runEval}
              type="button"
            >
              {isRunning ? "Running" : "Run eval"}
            </button>
          </>
        ) : null}
      </section>
    </div>
  );
}
