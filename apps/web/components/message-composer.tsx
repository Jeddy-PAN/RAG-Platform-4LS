"use client";

import type { FormEvent } from "react";
import { useState } from "react";

type MessageComposerProps = {
  disabled: boolean;
  isSending: boolean;
  onSend: (message: string) => Promise<void>;
};

export function MessageComposer({ disabled, isSending, onSend }: MessageComposerProps) {
  const [message, setMessage] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = message.trim();

    if (!trimmed || disabled || isSending) {
      return;
    }

    setMessage("");
    await onSend(trimmed);
  }

  return (
    <form className="message-composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="chat-message">
        Ask a question
      </label>
      <textarea
        disabled={disabled || isSending}
        id="chat-message"
        onChange={(event) => setMessage(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
        placeholder={disabled ? "Select a project to chat" : "Ask across the selected project"}
        rows={2}
        value={message}
      />
      <button disabled={disabled || isSending || !message.trim()} type="submit">
        Send
      </button>
    </form>
  );
}
