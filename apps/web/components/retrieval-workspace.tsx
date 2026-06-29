"use client";

import { useEffect, useState } from "react";
import { projectsApi, retrievalApi } from "@/lib/api";
import type { Project, RetrievalMode, RetrievalResponse, UUID } from "@/lib/types";
import { ErrorState } from "./error-state";
import { RetrievalResults } from "./retrieval-results";

export function RetrievalWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<UUID | "">("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(8);
  const [rerankerEnabled, setRerankerEnabled] = useState(false);
  const [rerankerCandidateLimit, setRerankerCandidateLimit] = useState(40);
  const [response, setResponse] = useState<RetrievalResponse | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;

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

  async function runRetrieval() {
    if (!selectedProjectId || !query.trim()) {
      return;
    }

    setIsRunning(true);
    setError(null);
    try {
      const result = await retrievalApi.query(selectedProjectId, {
        query,
        mode,
        top_k: topK,
        vector_weight: 0.65,
        keyword_weight: 0.35,
        similarity_threshold: 0,
        reranker_enabled: rerankerEnabled,
        reranker_candidate_limit: rerankerCandidateLimit
      });
      setResponse(result);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Retrieval failed");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="tool-page retrieval-page">
      <header className="retrieval-header">
        <a href="/">Back to workbench</a>
        <div>
          <p className="eyebrow">Retrieval Playground</p>
          <h1>Inspect retrieval before generation</h1>
        </div>
      </header>
      <div className="retrieval-layout">
        <aside className="tool-sidebar">
          <div className="sidebar-heading">
            <div>
              <span className="sidebar-label">Projects</span>
              <strong>{projects.length}</strong>
            </div>
            <div className="sidebar-actions">
              <button
                aria-label="Open retrieval settings"
                className="icon-button"
                onClick={() => setSettingsOpen(true)}
                type="button"
              >
                Settings
              </button>
            </div>
          </div>
          {projects.length === 0 ? (
            <p className="sidebar-empty">Create a project before testing retrieval.</p>
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
        </aside>

        <div className="retrieval-workspace-panel">
          {error ? <ErrorState message={error} /> : null}
          <section className="retrieval-query-panel">
            <div>
              <span className="sidebar-label">Selected project</span>
              <strong>{selectedProject?.name ?? "No project selected"}</strong>
            </div>
            <textarea
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Test retrieval before answer generation"
              rows={3}
              value={query}
            />
            <div className="retrieval-query-actions">
              <span>
                {mode} · top {topK}
                {rerankerEnabled ? " · rerank" : ""}
              </span>
              <button
                disabled={isRunning || !selectedProjectId || !query.trim()}
                onClick={runRetrieval}
                type="button"
              >
                {isRunning ? "Running" : "Run retrieval"}
              </button>
            </div>
          </section>
          <RetrievalResults response={response} />
        </div>
      </div>
      {settingsOpen ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setSettingsOpen(false)}>
          <section
            aria-modal="true"
            className="tool-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-heading">
              <div>
                <span className="sidebar-label">Retrieval</span>
                <strong>Settings</strong>
              </div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)} type="button">
                Close
              </button>
            </div>
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
                max={50}
                min={1}
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
          </section>
        </div>
      ) : null}
    </main>
  );
}
