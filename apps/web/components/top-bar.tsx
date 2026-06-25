import type { Project } from "@/lib/types";

type TopBarProps = {
  activeProject: Project | null;
};

export function TopBar({ activeProject }: TopBarProps) {
  return (
    <header className="top-bar">
      <a className="brand" href="/">
        <span className="brand-mark">4LS</span>
        <span>Local RAG Workbench</span>
      </a>
      <div className="top-bar-status">
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
