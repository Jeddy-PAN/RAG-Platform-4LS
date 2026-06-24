const modules = [
  "Projects",
  "Knowledge Base",
  "RAG Chat",
  "Retrieval Playground",
  "Evaluation Logs"
];

export default function HomePage() {
  return (
    <main>
      <section className="shell">
        <p className="eyebrow">Local RAG Workbench</p>
        <h1>Enterprise RAG Platform</h1>
        <p className="summary">
          A local, project-isolated knowledge platform for document ingestion,
          hybrid retrieval, cited answers, and RAG evaluation.
        </p>

        <div className="grid">
          {modules.map((module) => (
            <div className="module" key={module}>
              {module}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
