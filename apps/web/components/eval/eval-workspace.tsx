"use client";

import { useEffect, useMemo, useState } from "react";
import { documentsApi, evalApi, projectsApi, retrievalApi } from "@/lib/api";
import { buildEvalRunCsv, buildEvalRunJson, buildExportFilename } from "@/lib/eval-export";
import {
  buildEvalResultFilterOptions,
  filterEvalResults,
  type EvalResultFilter
} from "@/lib/eval-result-filters";
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
import { downloadTextFile } from "./eval-helpers";
import { EvalComparePanel } from "./eval-compare-panel";
import { EvalModals, type EvalModalType } from "./eval-modals";
import { EvalRunDetail } from "./eval-run-detail";
import { EvalRunHistory } from "./eval-run-history";
import { useEvalCompare } from "./use-eval-compare";

type EvalPanelView = "questions" | "history";

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
  const [resultFilter, setResultFilter] = useState<EvalResultFilter>("all");
  const [selectedRetrievalLog, setSelectedRetrievalLog] = useState<RetrievalLog | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [isLoadingRetrievalLog, setIsLoadingRetrievalLog] = useState(false);
  const [evalEditMode, setEvalEditMode] = useState(false);
  const [busyEvalIds, setBusyEvalIds] = useState<Set<UUID>>(new Set());
  const [modal, setModal] = useState<EvalModalType>(null);
  const [panelView, setPanelView] = useState<EvalPanelView>("questions");
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

  const {
    compareRunIds, loadingCompareRunIds,
    compare, compareMetricRows,
    resetCompareState, addRunToCompare, toggleCompareRun, exportCompareCsv,
  } = useEvalCompare(selectedProjectId, selectedDatasetId, run, setError);

  useEffect(() => {
    if (!error) {
      return;
    }

    const timeoutId = window.setTimeout(() => setError(null), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [error]);

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

  function exportRunCsv(currentRun: EvalRun) {
    downloadTextFile(
      buildExportFilename("eval run", currentRun.id, "csv"),
      buildEvalRunCsv(currentRun),
      "text/csv;charset=utf-8"
    );
  }

  function exportRunJson(currentRun: EvalRun) {
    downloadTextFile(
      buildExportFilename("eval run", currentRun.id, "json"),
      JSON.stringify(buildEvalRunJson(currentRun), null, 2),
      "application/json;charset=utf-8"
    );
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
      addRunToCompare(result);
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
      addRunToCompare(result);
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
                      className="mini-button danger"
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

        </aside>

        <div className="retrieval-workspace-panel">
          {error ? (
            <div className="eval-toast" role="status">
              <span>{error}</span>
              <button aria-label="Dismiss eval notice" onClick={() => setError(null)} type="button">
                Close
              </button>
            </div>
          ) : null}
          <section className="retrieval-query-panel">
            <div>
              <span className="sidebar-label">Eval target</span>
              <strong>{selectedDataset?.name ?? "No dataset selected"}</strong>
              <small>{selectedProject?.name ?? "No project selected"}</small>
            </div>
            <div className="eval-panel-tabs" role="tablist" aria-label="Eval panels">
              <button
                aria-selected={panelView === "questions"}
                className={panelView === "questions" ? "active" : ""}
                onClick={() => setPanelView("questions")}
                role="tab"
                type="button"
              >
                Questions
              </button>
              <button
                aria-selected={panelView === "history"}
                className={panelView === "history" ? "active" : ""}
                onClick={() => setPanelView("history")}
                role="tab"
                type="button"
              >
                History
              </button>
            </div>
            {panelView === "questions" ? (
              selectedDataset ? (
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
              ) : null
            ) : (
              <div className="eval-history-panel">
                <div className="retrieval-summary">
                  <strong>History</strong>
                  <span>{runs.length}</span>
                </div>
                <EvalRunHistory
                  runs={runs}
                  selectedRun={run}
                  compareRunIds={compareRunIds}
                  loadingCompareRunIds={loadingCompareRunIds}
                  isLoadingRun={isLoadingRun}
                  loadRunDetail={loadRunDetail}
                  toggleCompareRun={toggleCompareRun}
                />
              </div>
            )}
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
          <EvalComparePanel
            compare={compare}
            compareMetricRows={compareMetricRows}
            loadedCount={compare.runs.length}
            totalCount={compareRunIds.length}
            exportCompareCsv={exportCompareCsv}
            resetCompareState={resetCompareState}
          />
          {!run ? (
            <section className="retrieval-empty">
              Select a previous run or create a dataset, add questions, then run eval.
            </section>
          ) : (
            <EvalRunDetail
              run={run}
              resultFilter={resultFilter}
              setResultFilter={setResultFilter}
              resultFilterOptions={resultFilterOptions}
              filteredResults={filteredResults}
              questionsById={questionsById}
              documentNamesById={documentNamesById}
              avgGenerationLatency={avgGenerationLatency}
              exportRunCsv={exportRunCsv}
              exportRunJson={exportRunJson}
              isLoadingRetrievalLog={isLoadingRetrievalLog}
              loadRetrievalLog={loadRetrievalLog}
              selectedRetrievalLog={selectedRetrievalLog}
            />
          )}
        </div>
      </div>
      <EvalModals
        modal={modal}
        onClose={() => setModal(null)}
        datasetName={datasetName} setDatasetName={setDatasetName}
        createDataset={createDataset}
        question={question} setQuestion={setQuestion}
        expectedNotes={expectedNotes} setExpectedNotes={setExpectedNotes}
        expectedDocumentId={expectedDocumentId} setExpectedDocumentId={setExpectedDocumentId}
        expectedChunkId={expectedChunkId} setExpectedChunkId={setExpectedChunkId}
        addQuestion={addQuestion}
        documents={documents}
        selectedDatasetId={selectedDatasetId}
        mode={mode} setMode={setMode}
        topK={topK} setTopK={setTopK}
        rerankerEnabled={rerankerEnabled} setRerankerEnabled={setRerankerEnabled}
        rerankerCandidateLimit={rerankerCandidateLimit} setRerankerCandidateLimit={setRerankerCandidateLimit}
        judgeEnabled={judgeEnabled} setJudgeEnabled={setJudgeEnabled}
        runEval={runEval}
        isRunning={isRunning}
        selectedDataset={selectedDataset}
      />
    </main>
  );
}
