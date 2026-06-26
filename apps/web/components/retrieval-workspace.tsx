"use client";

import { useEffect, useState } from "react";
import { projectsApi, retrievalApi } from "@/lib/api";
import type { Project, RetrievalMode, RetrievalResponse, UUID } from "@/lib/types";
import { ErrorState } from "./error-state";
import { RetrievalControls } from "./retrieval-controls";
import { RetrievalResults } from "./retrieval-results";

export function RetrievalWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<UUID | "">("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(8);
  const [response, setResponse] = useState<RetrievalResponse | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        similarity_threshold: 0
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
        <RetrievalControls
          isRunning={isRunning}
          mode={mode}
          onModeChange={setMode}
          onProjectChange={setSelectedProjectId}
          onQueryChange={setQuery}
          onRun={runRetrieval}
          onTopKChange={setTopK}
          projects={projects}
          query={query}
          selectedProjectId={selectedProjectId}
          topK={topK}
        />
        <div>
          {error ? <ErrorState message={error} /> : null}
          <RetrievalResults response={response} />
        </div>
      </div>
    </main>
  );
}
