"use client";

import type { ChatMessage, FeedbackRating, UUID } from "@/lib/types";
import { CitationList } from "./citation-list";
import { FeedbackControls } from "./feedback-controls";

type MessageListProps = {
  messages: ChatMessage[];
  conversationId: UUID | null;
  isSending: boolean;
  onFeedback: (messageId: UUID, rating: FeedbackRating) => Promise<void>;
};

export function MessageList({ messages, conversationId, isSending, onFeedback }: MessageListProps) {
  return (
    <div className="message-list">
      {messages.map((message) => (
        <article className={`message message-${message.role}`} key={message.id}>
          <div className="message-bubble">
            <p>{message.content}</p>
          </div>
          {message.role === "assistant" ? (
            <div className="assistant-detail">
              <CitationList citations={message.citations ?? []} />
              {message.assistantMessageId && conversationId ? (
                <FeedbackControls
                  disabled={!conversationId}
                  onSubmit={(rating) => onFeedback(message.assistantMessageId as UUID, rating)}
                />
              ) : null}
            </div>
          ) : null}
        </article>
      ))}
      {isSending ? (
        <article className="message message-assistant">
          <div className="message-bubble loading-answer">Searching local knowledge</div>
        </article>
      ) : null}
    </div>
  );
}
