"use client";

import { useEffect, useMemo, useState } from "react";
import { documentsApi, evalApi, projectsApi, retrievalApi } from "@/lib/api";
import {
  buildEvalRunCompare,
  type EvalRunCompareCell
} from "@/lib/eval-run-compare";
import {
  buildEvalResultFilterOptions,
  filterEvalResults,
  type EvalResultFilter
} from "@/lib/eval-result-filters";
import { shortId } from "@/lib/format";
import type {
  DocumentItem,
  EvalDataset,
  EvalQuestion,
  EvalRun,
  EvalRunSummary,
  Project,
  RetrievalLog,
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

function formatLatency(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "0 ms";
  }
  return `${Math.round(value)} ms`;
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatCellOutcome(cell: EvalRunCompareCell) {
  if (!cell.resultId) {
    return "Missing";
  }
  if (cell.refused) {
    return "Refused";
  }
  return cell.answerMatched ? "Pass" : "Fail";
}

function getCellClassName(cell: EvalRunCompareCell) {
  if (!cell.resultId) {
    return "eval-compare-cell missing";
  }
  if (cell.refused) {
    return "eval-compare-cell refused";
  }
  return cell.answerMatched ? "eval-compare-cell pass" : "eval-compare-cell fail";
}

export function EvalWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<UUID | "">("");
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<UUID | "">("");
  const [questions, setQuestions] = useState<EvalQuestion[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [datasetName, setDatasetName] = useState("");
  const [question, setQuestion] = useState("");
  const [expectedNotes, setExpectedNotes] = useState("");
  const [expectedDocumentId, setExpectedDocumentId] = useState("");
  const [expectedChunkId, setExpectedChunkId] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(8);
  const [rerankerEnabled, setRerankerEnabled] = useState(false);
  const [rerankerCandidateLimit, setRerankerCandidateLimit] = useState(40);
  const [judgeEnabled, setJudgeEnabled] = useState(false);
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [compareRunIds, setCompareRunIds] = useState<UUID[]>([]);
  const [compareRunsById, setCompareRunsById] = useState<Record<UUID, EvalRun>>({});
  const [loadingCompareRunIds, setLoadingCompareRunIds] = useState<Set<UUID>>(new Set());
  const [resultFilter, setResultFilter] = useState<EvalResultFilter>("all");
  const [selectedRetrievalLog, setSelectedRetrievalLog] = useState<RetrievalLog | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [isLoadingRetrievalLog, setIsLoadingRetrievalLog] = useState(false);
  const [evalEditMode, setEvalEditMode] = useState(false);
  const [busyEvalIds, setBusyEvalIds] = useState<Set<UUID>>(new Set());
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

  const documentNamesById = useMemo(
    () => new Map(documents.map((document) => [document.id, document.filename])),
    [documents]
  );

  const questionsById = useMemo(
    () => new Map(questions.map((questionItem) => [questionItem.id, questionItem])),
    [questions]
  );

  const resultFilterOptions = useMemo(
    () => buildEvalResultFilterOptions(run?.results ?? []),
    [run?.results]
  );

  const filteredResults = useMemo(
    () => filterEvalResults(run?.results ?? [], resultFilter),
    [run?.results, resultFilter]
  );

  const avgGenerationLatency = useMemo(() => {
    const latencies = (run?.results ?? [])
      .map((result) => result.generation_latency_ms)
      .filter((value): value is number => typeof value === "number");

    if (latencies.length === 0) {
      return null;
    }

    return latencies.reduce((total, value) => total + value, 0) / latencies.length;
  }, [run?.results]);

  const compareRuns = useMemo(
    () =>
      compareRunIds
        .map((runId) => (run?.id === runId ? run : compareRunsById[runId]))
        .filter((item): item is EvalRun => Boolean(item)),
    [compareRunIds, compareRunsById, run]
  );

  const compare = useMemo(() => buildEvalRunCompare(compareRuns), [compareRuns]);

  const compareMetricRows = useMemo(
    () => [
      {
        label: "Hit rate",
        values: compare.runs.map((item) => formatRate(item.hitRate))
      },
      {
        label: "Citation",
        values: compare.runs.map((item) => formatRate(item.citationCoverageRate))
      },
      {
        label: "Answer match",
        values: compare.runs.map((item) => formatRate(item.answerMatchRate))
      },
      {
        label: "Judge",
        values: compare.runs.map((item) => formatRate(item.judgeMatchRate))
      },
      {
        label: "Avg retrieval",
        values: compare.runs.map((item) => formatLatency(item.avgRetrievalLatencyMs))
      },
      {
        label: "Avg generation",
        values: compare.runs.map((item) => formatLatency(item.avgGenerationLatencyMs))
      }
    ],
    [compare.runs]
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
    setSelectedRetrievalLog(null);
    setResultFilter("all");
    resetCompareState();
    setDatasets([]);
    setSelectedDatasetId("");
    if (selectedProjectId) {
      void loadDatasets(selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    async function loadDocuments(projectId: UUID) {
      try {
        const documentList = await documentsApi.list(projectId);
        setDocuments(documentList);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load documents");
      }
    }

    setDocuments([]);
    setExpectedDocumentId("");
    if (selectedProjectId) {
      void loadDocuments(selectedProjectId);
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
    setSelectedRetrievalLog(null);
    setResultFilter("all");
    resetCompareState();
    setRuns([]);
    setQuestions([]);
    if (selectedProjectId && selectedDatasetId) {
      void loadRuns(selectedProjectId, selectedDatasetId);
    }
  }, [selectedProjectId, selectedDatasetId]);

  useEffect(() => {
    async function loadQuestions(projectId: UUID, datasetId: UUID) {
      try {
        const questionList = await evalApi.listQuestions(projectId, datasetId);
        setQuestions(questionList);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load eval questions");
      }
    }

    setQuestions([]);
    if (selectedProjectId && selectedDatasetId) {
      void loadQuestions(selectedProjectId, selectedDatasetId);
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

  async function refreshQuestions(projectId: UUID, datasetId: UUID) {
    const questionList = await evalApi.listQuestions(projectId, datasetId);
    setQuestions(questionList);
  }

  function resetCompareState() {
    setCompareRunIds([]);
    setCompareRunsById({});
    setLoadingCompareRunIds(new Set());
  }

  async function ensureCompareRunDetail(runId: UUID) {
    if (!selectedProjectId || !selectedDatasetId || run?.id === runId || compareRunsById[runId]) {
      return;
    }

    setLoadingCompareRunIds((current) => new Set(current).add(runId));
    setError(null);
    try {
      const result = await evalApi.getRun(selectedProjectId, selectedDatasetId, runId);
      setCompareRunsById((current) => ({ ...current, [runId]: result }));
    } catch (loadError) {
      setCompareRunIds((current) => current.filter((id) => id !== runId));
      setError(loadError instanceof Error ? loadError.message : "Unable to load compare run");
    } finally {
      setLoadingCompareRunIds((current) => {
        const next = new Set(current);
        next.delete(runId);
        return next;
      });
    }
  }

  function toggleCompareRun(runId: UUID) {
    if (compareRunIds.includes(runId)) {
      setCompareRunIds((current) => current.filter((id) => id !== runId));
      return;
    }

    if (compareRunIds.length >= 4) {
      return;
    }

    setCompareRunIds((current) => [...current, runId]);
    void ensureCompareRunDetail(runId);
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
      await refreshQuestions(selectedProjectId, selectedDatasetId);
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
        keyword_weight: 0.35,
        reranker_enabled: rerankerEnabled,
        reranker_candidate_limit: rerankerCandidateLimit,
        judge_enabled: judgeEnabled
      });
      setRun(result);
      setCompareRunsById((current) => ({ ...current, [result.id]: result }));
      setSelectedRetrievalLog(null);
      setResultFilter("all");
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
      setCompareRunsById((current) => ({ ...current, [result.id]: result }));
      setSelectedRetrievalLog(null);
      setResultFilter("all");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load eval run");
    } finally {
      setIsLoadingRun(false);
    }
  }

  async function deleteDataset(dataset: EvalDataset) {
    if (!selectedProjectId || !confirm(`Delete eval dataset "${dataset.name}"?`)) {
      return;
    }

    setBusyEvalIds((current) => new Set(current).add(dataset.id));
    setError(null);
    try {
      await evalApi.deleteDataset(selectedProjectId, dataset.id);
      await refreshDatasets(selectedProjectId);
      setRun(null);
      setSelectedRetrievalLog(null);
      setResultFilter("all");
      resetCompareState();
      setRuns([]);
      setQuestions([]);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete dataset");
    } finally {
      setBusyEvalIds((current) => {
        const next = new Set(current);
        next.delete(dataset.id);
        return next;
      });
    }
  }

  async function loadRetrievalLog(logId: UUID | undefined) {
    if (!selectedProjectId || !logId) {
      return;
    }

    setIsLoadingRetrievalLog(true);
    setError(null);
    try {
      const log = await retrievalApi.getLog(selectedProjectId, logId);
      setSelectedRetrievalLog(log);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load retrieval log");
    } finally {
      setIsLoadingRetrievalLog(false);
    }
  }

  async function deleteQuestion(questionItem: EvalQuestion) {
    if (
      !selectedProjectId ||
      !selectedDatasetId ||
      !confirm(`Delete question "${questionItem.question}"?`)
    ) {
      return;
    }

    setBusyEvalIds((current) => new Set(current).add(questionItem.id));
    setError(null);
    try {
      await evalApi.deleteQuestion(selectedProjectId, selectedDatasetId, questionItem.id);
      await refreshQuestions(selectedProjectId, selectedDatasetId);
      await refreshDatasets(selectedProjectId, selectedDatasetId);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete question");
    } finally {
      setBusyEvalIds((current) => {
        const next = new Set(current);
        next.delete(questionItem.id);
        return next;
      });
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
              <button
                aria-label="Toggle eval edit mode"
                className={`icon-button ${evalEditMode ? "active" : ""}`}
                onClick={() => setEvalEditMode((value) => !value)}
                type="button"
              >
                Edit
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
                  {evalEditMode ? (
                    <button
                      className="mini-button danger tool-row-action"
                      disabled={busyEvalIds.has(dataset.id)}
                      onClick={() => deleteDataset(dataset)}
                      type="button"
                    >
                      Delete
                    </button>
                  ) : null}
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
              {runs.map((item) => {
                const isCompareSelected = compareRunIds.includes(item.id);
                const isCompareDisabled = !isCompareSelected && compareRunIds.length >= 4;
                const isCompareLoading = loadingCompareRunIds.has(item.id);

                return (
                  <div
                    className={run?.id === item.id ? "eval-run-row active" : "eval-run-row"}
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
            {selectedDataset ? (
              <div className="eval-question-panel">
                <div className="retrieval-summary">
                  <strong>Questions</strong>
                  <span>{questions.length}</span>
                </div>
                {questions.length === 0 ? (
                  <p className="sidebar-empty">No questions in this dataset.</p>
                ) : (
                  <ul className="eval-question-list">
                    {questions.map((questionItem) => (
                      <li key={questionItem.id}>
                        <span>{questionItem.question}</span>
                        <small>
                          {questionItem.expected_document_id
                            ? documentNamesById.get(questionItem.expected_document_id) ??
                              questionItem.expected_document_id
                            : "Any document"}
                          {questionItem.expected_answer_notes
                            ? ` · ${questionItem.expected_answer_notes}`
                            : ""}
                        </small>
                        {evalEditMode ? (
                          <button
                            className="mini-button danger"
                            disabled={busyEvalIds.has(questionItem.id)}
                            onClick={() => deleteQuestion(questionItem)}
                            type="button"
                          >
                            Delete
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
            <div className="retrieval-query-actions">
              <span>
                {mode} · top {topK}
                {rerankerEnabled ? " · rerank" : ""}
                {judgeEnabled ? " · judge" : ""}
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
          {compareRunIds.length > 0 ? (
            <section className="eval-compare-panel">
              <div className="eval-compare-heading">
                <div>
                  <span className="sidebar-label">Run compare</span>
                  <strong>
                    {compare.runs.length}/{compareRunIds.length} loaded
                  </strong>
                </div>
                <button className="mini-button" onClick={resetCompareState} type="button">
                  Clear
                </button>
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
          ) : null}
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
                            onClick={() => loadRetrievalLog(result.result_metadata.retrieval_log_id)}
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
      ) : null}
    </main>
  );
}
