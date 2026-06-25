"use client";

import type { ChatMessage, FeedbackRating, Project, UUID } from "@/lib/types";
import { ChatEmptyState } from "./chat-empty-state";
import { ErrorState } from "./error-state";
import { MessageComposer } from "./message-composer";
import { MessageList } from "./message-list";
import { RetrievalFloatingButton } from "./retrieval-floating-button";

type ChatWorkspaceProps = {
  activeProject: Project | null;
  messages: ChatMessage[];
  conversationId: UUID | null;
  isSending: boolean;
  error: string | null;
  onSend: (message: string) => Promise<void>;
  onFeedback: (messageId: UUID, rating: FeedbackRating) => Promise<void>;
};

export function ChatWorkspace({
  activeProject,
  messages,
  conversationId,
  isSending,
  error,
  onSend,
  onFeedback
}: ChatWorkspaceProps) {
  const disabled = !activeProject;

  return (
    <main className="chat-workspace">
      {messages.length === 0 ? (
        <ChatEmptyState disabled={disabled} isSending={isSending} onSend={onSend} />
      ) : (
        <section className="active-chat">
          <div className="conversation-header">
            <span>Chat</span>
            <strong>{activeProject?.name ?? "No project"}</strong>
          </div>
          <MessageList
            conversationId={conversationId}
            isSending={isSending}
            messages={messages}
            onFeedback={onFeedback}
          />
          <MessageComposer disabled={disabled} isSending={isSending} onSend={onSend} />
        </section>
      )}
      {error ? <ErrorState message={error} /> : null}
      <RetrievalFloatingButton />
    </main>
  );
}
