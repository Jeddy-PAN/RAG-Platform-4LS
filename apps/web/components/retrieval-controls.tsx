"use client";

import type { FormEvent } from "react";
import type { Project, RetrievalMode, UUID } from "@/lib/types";

type RetrievalControlsProps = {
  projects: Project[];
  selectedProjectId: UUID | "";
  mode: RetrievalMode;
  query: string;
  topK: number;
  isRunning: boolean;
  onProjectChange: (projectId: UUID) => void;
  onModeChange: (mode: RetrievalMode) => void;
  onQueryChange: (query: string) => void;
  onTopKChange: (topK: number) => void;
  onRun: () => Promise<void>;
};

export function RetrievalControls({
  projects,
  selectedProjectId,
  mode,
  query,
  topK,
  isRunning,
  onProjectChange,
  onModeChange,
  onQueryChange,
  onTopKChange,
  onRun
}: RetrievalControlsProps) {
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onRun();
  }

  return (
    <form className="retrieval-controls" onSubmit={handleSubmit}>
      <label>
        Project
        <select
          onChange={(event) => onProjectChange(event.target.value)}
          required
          value={selectedProjectId}
        >
          <option value="">Select project</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Query
        <textarea
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Test retrieval before answer generation"
          required
          rows={3}
          value={query}
        />
      </label>
      <div className="retrieval-grid">
        <label>
          Mode
          <select onChange={(event) => onModeChange(event.target.value as RetrievalMode)} value={mode}>
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
            onChange={(event) => onTopKChange(Number(event.target.value))}
            type="number"
            value={topK}
          />
        </label>
      </div>
      <button disabled={isRunning || !selectedProjectId || !query.trim()} type="submit">
        {isRunning ? "Running" : "Run retrieval"}
      </button>
    </form>
  );
}
