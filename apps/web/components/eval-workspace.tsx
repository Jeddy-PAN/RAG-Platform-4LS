"use client";

import { useEffect, useMemo, useState } from "react";
import { evalApi, projectsApi } from "@/lib/api";
import type {
  EvalDataset,
  EvalRun,
  EvalRunSummary,
  Project,
  RetrievalMode,
  UUID
} from "@/lib/types";
import { ErrorState } from "./error-state";

function formatRate(value: number | undefined) {
  if (typeof value !== "number") {
    return "0%";
  }
  return `${Math.round(value * 100)}%`;
}

function formatLatency(value: number | undefined) {
  if (typeof value !== "number") {
    return "0 ms";
  }
  return `${Math.round(value)} ms`;
}

export function EvalWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<UUID | "">("");
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<UUID | "">("");
  const [datasetName, setDatasetName] = useState("");
  const [question, setQuestion] = useState("");
  const [expectedNotes, setExpectedNotes] = useState("");
  const [expectedDocumentId, setExpectedDocumentId] = useState("");
  const [expectedChunkId, setExpectedChunkId] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(8);
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [modal, setModal] = useState<"dataset" | "question" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId]
  );

  useEffect(() => {
    async function loadProjects() {
      try {
        const projectList = await projectsApi.list();
        setProjects(projectList);
        setSelectedProjectId(projectList[0]?.id ?? "");
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load projects");
      }
    }

    void loadProjects();
  }, []);

  useEffect(() => {
    async function loadDatasets(projectId: UUID) {
      try {
        const datasetList = await evalApi.listDatasets(projectId);
        setDatasets(datasetList);
        setSelectedDatasetId(datasetList[0]?.id ?? "");
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load eval datasets");
      }
    }

    setRun(null);
    setDatasets([]);
    setSelectedDatasetId("");
    if (selectedProjectId) {
      void loadDatasets(selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    async function loadRuns(projectId: UUID, datasetId: UUID) {
      try {
        const runList = await evalApi.listRuns(projectId, datasetId);
        setRuns(runList);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load eval runs");
      }
    }

    setRun(null);
    setRuns([]);
    if (selectedProjectId && selectedDatasetId) {
      void loadRuns(selectedProjectId, selectedDatasetId);
    }
  }, [selectedProjectId, selectedDatasetId]);

  async function refreshDatasets(projectId: UUID, nextDatasetId?: UUID) {
    const datasetList = await evalApi.listDatasets(projectId);
    setDatasets(datasetList);
    setSelectedDatasetId(nextDatasetId ?? datasetList[0]?.id ?? "");
  }

  async function refreshRuns(projectId: UUID, datasetId: UUID) {
    const runList = await evalApi.listRuns(projectId, datasetId);
    setRuns(runList);
  }

  async function createDataset() {
    if (!selectedProjectId || !datasetName.trim()) {
      return;
    }

    setError(null);
    try {
      const dataset = await evalApi.createDataset(selectedProjectId, {
        name: datasetName,
        description: null
      });
      setDatasetName("");
      await refreshDatasets(selectedProjectId, dataset.id);
      setModal(null);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create dataset");
    }
  }

  async function addQuestion() {
    if (!selectedProjectId || !selectedDatasetId || !question.trim()) {
      return;
    }

    setError(null);
    try {
      await evalApi.createQuestion(selectedProjectId, selectedDatasetId, {
        question,
        expected_answer_notes: expectedNotes.trim() || null,
        expected_document_id: expectedDocumentId.trim() || null,
        expected_chunk_id: expectedChunkId.trim() || null,
        should_answer: true
      });
      setQuestion("");
      setExpectedNotes("");
      setExpectedDocumentId("");
      setExpectedChunkId("");
      await refreshDatasets(selectedProjectId, selectedDatasetId);
      setModal(null);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to add question");
    }
  }

  async function runEval() {
    if (!selectedProjectId || !selectedDatasetId) {
      return;
    }

    setIsRunning(true);
    setError(null);
    try {
      const result = await evalApi.runDataset(selectedProjectId, selectedDatasetId, {
        retrieval_mode: mode,
        top_k: topK,
        vector_weight: 0.65,
        keyword_weight: 0.35
      });
      setRun(result);
      await refreshRuns(selectedProjectId, selectedDatasetId);
      setModal(null);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Eval run failed");
    } finally {
      setIsRunning(false);
    }
  }

  async function loadRunDetail(runId: UUID) {
    if (!selectedProjectId || !selectedDatasetId) {
      return;
    }

    setIsLoadingRun(true);
    setError(null);
    try {
      const result = await evalApi.getRun(selectedProjectId, selectedDatasetId, runId);
      setRun(result);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load eval run");
    } finally {
      setIsLoadingRun(false);
    }
  }

  return (
    <main className="tool-page retrieval-page">
      <header className="retrieval-header">
        <a href="/">Back to workbench</a>
        <div>
          <p className="eyebrow">Eval Harness</p>
          <h1>Measure retrieval and grounded answers</h1>
        </div>
      </header>

      <div className="retrieval-layout">
        <aside className="tool-sidebar eval-sidebar">
          <div className="sidebar-heading">
            <div>
              <span className="sidebar-label">Projects</span>
              <strong>{projects.length}</strong>
            </div>
          </div>
          {projects.length === 0 ? (
            <p className="sidebar-empty">Create a project before running eval.</p>
          ) : (
            <ul className="tool-list">
              {projects.map((project) => (
                <li key={project.id}>
                  <button
                    className={project.id === selectedProjectId ? "selected" : ""}
                    onClick={() => setSelectedProjectId(project.id)}
                    type="button"
                  >
                    <span>{project.name}</span>
                    {project.description ? <small>{project.description}</small> : null}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="sidebar-heading eval-section-heading">
            <div>
              <span className="sidebar-label">Datasets</span>
              <strong>{datasets.length}</strong>
            </div>
            <div className="sidebar-actions">
              <button
                aria-label="Create eval dataset"
                className="icon-button"
                disabled={!selectedProjectId}
                onClick={() => setModal("dataset")}
                type="button"
              >
                +
              </button>
              <button
                aria-label="Add eval question"
                className="icon-button"
                disabled={!selectedDatasetId}
                onClick={() => setModal("question")}
                type="button"
              >
                Q
              </button>
              <button
                aria-label="Run eval"
                className="icon-button"
                disabled={!selectedDatasetId || isRunning || !selectedDataset?.question_count}
                onClick={() => setModal("run")}
                type="button"
              >
                Run
              </button>
            </div>
          </div>
          {datasets.length === 0 ? (
            <p className="sidebar-empty">Create a dataset to add questions.</p>
          ) : (
            <ul className="tool-list">
              {datasets.map((dataset) => (
                <li key={dataset.id}>
                  <button
                    className={dataset.id === selectedDatasetId ? "selected" : ""}
                    onClick={() => setSelectedDatasetId(dataset.id)}
                    type="button"
                  >
                    <span>{dataset.name}</span>
                    <small>{dataset.question_count} questions</small>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="sidebar-heading eval-section-heading">
            <div>
              <span className="sidebar-label">Recent runs</span>
              <strong>{runs.length}</strong>
            </div>
          </div>
          {runs.length > 0 ? (
            <div className="eval-run-list compact">
              {runs.map((item) => (
                <button
                  className={run?.id === item.id ? "active" : ""}
                  disabled={isLoadingRun}
                  key={item.id}
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
              ))}
            </div>
          ) : (
            <p className="sidebar-empty">No runs for this dataset.</p>
          )}
        </aside>

        <div className="retrieval-workspace-panel">
          {error ? <ErrorState message={error} /> : null}
          <section className="retrieval-query-panel">
            <div>
              <span className="sidebar-label">Eval target</span>
              <strong>{selectedDataset?.name ?? "No dataset selected"}</strong>
              <small>{selectedProject?.name ?? "No project selected"}</small>
            </div>
            <div className="retrieval-query-actions">
              <span>
                {mode} · top {topK}
              </span>
              <button
                disabled={!selectedDatasetId || isRunning || !selectedDataset?.question_count}
                onClick={() => setModal("run")}
                type="button"
              >
                {isRunning ? "Running" : "Run eval"}
              </button>
            </div>
          </section>
          {!run ? (
            <section className="retrieval-empty">
              Select a previous run or create a dataset, add questions, then run eval.
            </section>
          ) : (
            <section className="retrieval-results">
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
                  <span>Avg retrieval</span>
                  <strong>{formatLatency(run.metrics.avg_retrieval_latency_ms)}</strong>
                </div>
              </div>
              <ol>
                {run.results.map((result) => (
                  <li key={result.id}>
                    <div className="result-heading">
                      <strong>{result.question}</strong>
                      <span>score {result.score ?? 0}</span>
                    </div>
                    <p>{result.answer}</p>
                    <div className="score-row">
                      hit {String(result.hit)} · citation {String(result.citation_covered)} ·
                      answer {String(result.answer_matched)} · refused {String(result.refused)}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </div>
      </div>
      {modal ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setModal(null)}>
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
              <button className="icon-button" onClick={() => setModal(null)} type="button">
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
                  Expected document id
                  <input
                    onChange={(event) => setExpectedDocumentId(event.target.value)}
                    placeholder="optional"
                    type="text"
                    value={expectedDocumentId}
                  />
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
      ) : null}
    </main>
  );
}
