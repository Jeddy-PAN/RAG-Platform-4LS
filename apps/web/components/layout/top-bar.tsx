import type { Project, SystemConfig } from "@/lib/types";

type TopBarProps = {
  activeProject: Project | null;
  systemConfig: SystemConfig | null;
};

export function TopBar({ activeProject, systemConfig }: TopBarProps) {
  return (
    <header className="top-bar">
      <a className="brand" href="/">
        <span className="brand-mark">4LS</span>
        <span>Local RAG Workbench</span>
      </a>
      <div className="top-bar-status">
        {systemConfig ? (
          <span className="provider-status">
            Emb {systemConfig.embedding.provider}:{systemConfig.embedding.model}
            <span>Chat {systemConfig.llm.model}</span>
          </span>
        ) : null}
        {activeProject ? (
          <>
            <span className="muted">Active project</span>
            <strong>{activeProject.name}</strong>
          </>
        ) : (
          <span className="muted">No project selected</span>
        )}
      </div>
    </header>
  );
}
