"use client";

import { useEffect, useMemo, useState } from "react";
import { evalApi, projectsApi } from "@/lib/api";
import type { EvalDataset, EvalRun, Project, RetrievalMode, UUID } from "@/lib/types";
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
  const [run, setRun] = useState<EvalRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  async function refreshDatasets(projectId: UUID, nextDatasetId?: UUID) {
    const datasetList = await evalApi.listDatasets(projectId);
    setDatasets(datasetList);
    setSelectedDatasetId(nextDatasetId ?? datasetList[0]?.id ?? "");
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
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Eval run failed");
    } finally {
      setIsRunning(false);
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
        <section className="retrieval-controls">
          <label>
            Project
            <select
              onChange={(event) => setSelectedProjectId(event.target.value)}
              value={selectedProjectId}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Dataset
            <select
              onChange={(event) => setSelectedDatasetId(event.target.value)}
              value={selectedDatasetId}
            >
              <option value="">Select dataset</option>
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.name} ({dataset.question_count})
                </option>
              ))}
            </select>
          </label>

          <div className="eval-inline">
            <input
              onChange={(event) => setDatasetName(event.target.value)}
              placeholder="New dataset"
              type="text"
              value={datasetName}
            />
            <button disabled={!datasetName.trim()} onClick={createDataset} type="button">
              Add
            </button>
          </div>

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

          <div className="retrieval-grid">
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
          </div>

          <button
            disabled={!selectedDatasetId || isRunning || !selectedDataset?.question_count}
            onClick={runEval}
            type="button"
          >
            {isRunning ? "Running" : "Run eval"}
          </button>
        </section>

        <div>
          {error ? <ErrorState message={error} /> : null}
          {!run ? (
            <section className="retrieval-empty">
              Select or create a dataset, add questions, then run eval.
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
    </main>
  );
}
