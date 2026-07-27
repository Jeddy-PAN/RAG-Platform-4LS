"use client";

import type { ChangeEvent, FormEvent } from "react";
import { useLayoutEffect, useRef, useState } from "react";
import { getAutosizeTextareaHeight } from "@/lib/textarea-autosize";

type MessageComposerProps = {
  disabled: boolean;
  isSending: boolean;
  onSend: (message: string) => Promise<void>;
};

export function MessageComposer({ disabled, isSending, onSend }: MessageComposerProps) {
  const [message, setMessage] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  function resizeTextarea() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "auto";
    textarea.style.height = getAutosizeTextareaHeight(textarea.scrollHeight);
  }

  function handleChange(event: ChangeEvent<HTMLTextAreaElement>) {
    setMessage(event.target.value);
  }

  useLayoutEffect(() => {
    resizeTextarea();
  }, [message]);

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
        onChange={handleChange}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
        placeholder={disabled ? "Select a project to chat" : "Ask across the selected project"}
        ref={textareaRef}
        rows={2}
        value={message}
      />
      <button disabled={disabled || isSending || !message.trim()} type="submit">
        Send
      </button>
    </form>
  );
}
