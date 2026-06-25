import { MessageComposer } from "./message-composer";

type ChatEmptyStateProps = {
  disabled: boolean;
  isSending: boolean;
  onSend: (message: string) => Promise<void>;
};

export function ChatEmptyState({ disabled, isSending, onSend }: ChatEmptyStateProps) {
  return (
    <section className="chat-empty-state">
      <div className="chat-title-block">
        <p className="eyebrow">Project knowledge</p>
        <h1>Ask your local knowledge base</h1>
        <p>Ground answers in uploaded documents with citations.</p>
      </div>
      <MessageComposer disabled={disabled} isSending={isSending} onSend={onSend} />
    </section>
  );
}
