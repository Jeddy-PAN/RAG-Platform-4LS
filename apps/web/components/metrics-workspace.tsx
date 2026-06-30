"use client";

import { useEffect, useMemo, useState } from "react";
import { metricsApi, projectsApi } from "@/lib/api";
import type { ChatMetricsResponse, Project, UUID } from "@/lib/types";
import { ErrorState } from "./error-state";

function formatLatency(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "0 ms";
  }
  return `${Math.round(value)} ms`;
}

function formatAverage(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "0";
  }
  return value.toFixed(1);
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function MetricsWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<UUID | "">("");
  const [metrics, setMetrics] = useState<ChatMetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
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
    async function loadMetrics(projectId: UUID) {
      setIsLoading(true);
      setError(null);
      try {
        setMetrics(await metricsApi.chat(projectId));
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load metrics");
      } finally {
        setIsLoading(false);
      }
    }

    setMetrics(null);
    if (selectedProjectId) {
      void loadMetrics(selectedProjectId);
    }
  }, [selectedProjectId]);

  return (
    <main className="tool-page metrics-page">
      <header className="retrieval-header">
        <a href="/">Back to workbench</a>
        <div>
          <p className="eyebrow">Metrics</p>
          <h1>Observe chat performance</h1>
        </div>
      </header>

      <div className="retrieval-layout">
        <aside className="tool-sidebar">
          <div className="sidebar-heading">
            <div>
              <span className="sidebar-label">Projects</span>
              <strong>{projects.length}</strong>
            </div>
          </div>
          {projects.length === 0 ? (
            <p className="sidebar-empty">Create a project before viewing metrics.</p>
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

        <section className="metrics-workspace-panel">
          {error ? <ErrorState message={error} /> : null}
          <div className="retrieval-query-panel">
            <div>
              <span className="sidebar-label">Metrics target</span>
              <strong>{selectedProject?.name ?? "No project selected"}</strong>
              <small>{isLoading ? "Loading metrics" : "Recent successful chat requests"}</small>
            </div>
          </div>

          {metrics ? (
            <>
              <div className="metrics-cards">
                <div>
                  <span>Requests</span>
                  <strong>{metrics.summary.request_count}</strong>
                </div>
                <div>
                  <span>Avg total</span>
                  <strong>{formatLatency(metrics.summary.avg_latency_ms)}</strong>
                </div>
                <div>
                  <span>Avg retrieval</span>
                  <strong>{formatLatency(metrics.summary.avg_retrieval_latency_ms)}</strong>
                </div>
                <div>
                  <span>Avg generation</span>
                  <strong>{formatLatency(metrics.summary.avg_generation_latency_ms)}</strong>
                </div>
                <div>
                  <span>Avg citations</span>
                  <strong>{formatAverage(metrics.summary.avg_citation_count)}</strong>
                </div>
              </div>

              <div className="metrics-table-panel">
                <div className="retrieval-summary">
                  <strong>Recent requests</strong>
                  <span>{metrics.items.length}</span>
                </div>
                {metrics.items.length === 0 ? (
                  <p className="sidebar-empty">No chat requests recorded for this project yet.</p>
                ) : (
                  <div className="metrics-table-scroll">
                    <table className="metrics-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Model</th>
                          <th>Total</th>
                          <th>Retrieval</th>
                          <th>Generation</th>
                          <th>Citations</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.items.map((item) => (
                          <tr key={item.id}>
                            <td>{formatDateTime(item.created_at)}</td>
                            <td>{item.model}</td>
                            <td>{formatLatency(item.latency_ms)}</td>
                            <td>{formatLatency(item.retrieval_latency_ms)}</td>
                            <td>{formatLatency(item.generation_latency_ms)}</td>
                            <td>{item.citation_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : (
            <section className="retrieval-empty">
              Select a project to inspect recent chat request metrics.
            </section>
          )}
        </section>
      </div>
    </main>
  );
}
