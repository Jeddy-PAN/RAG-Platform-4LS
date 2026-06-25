"use client";

import { useState } from "react";
import type { FeedbackRating } from "@/lib/types";

type FeedbackControlsProps = {
  disabled: boolean;
  onSubmit: (rating: FeedbackRating) => Promise<void>;
};

export function FeedbackControls({ disabled, onSubmit }: FeedbackControlsProps) {
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function submit(nextRating: FeedbackRating) {
    setIsSaving(true);
    try {
      await onSubmit(nextRating);
      setRating(nextRating);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="feedback-controls" aria-label="Answer feedback">
      <button
        aria-pressed={rating === "positive"}
        disabled={disabled || isSaving}
        onClick={() => submit("positive")}
        type="button"
      >
        Helpful
      </button>
      <button
        aria-pressed={rating === "negative"}
        disabled={disabled || isSaving}
        onClick={() => submit("negative")}
        type="button"
      >
        Not helpful
      </button>
    </div>
  );
}
