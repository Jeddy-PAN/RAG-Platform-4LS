"use client";

import type { ChangeEvent, DragEvent } from "react";
import { useRef, useState } from "react";

type SidebarUploadZoneProps = {
  disabled: boolean;
  isUploading: boolean;
  onUpload: (files: File[]) => void;
};

const ACCEPTED_TYPES = ".pdf,.docx,.txt,.xlsx";

export function SidebarUploadZone({ disabled, isUploading, onUpload }: SidebarUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function submitFiles(fileList: FileList | null) {
    if (!fileList || disabled) {
      return;
    }

    onUpload(Array.from(fileList));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    submitFiles(event.dataTransfer.files);
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    submitFiles(event.target.files);
    event.target.value = "";
  }

  return (
    <section
      className={`upload-zone ${isDragging ? "dragging" : ""} ${disabled ? "disabled" : ""}`}
      onDragLeave={() => setIsDragging(false)}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setIsDragging(true);
        }
      }}
      onDrop={handleDrop}
    >
      <input
        accept={ACCEPTED_TYPES}
        disabled={disabled || isUploading}
        hidden
        multiple
        onChange={handleInput}
        ref={inputRef}
        type="file"
      />
      <div>
        <strong>{disabled ? "Select a project first" : "Drop project files here"}</strong>
        <p>PDF, DOCX, TXT, XLSX</p>
      </div>
      <button
        className="secondary-button"
        disabled={disabled || isUploading}
        onClick={() => inputRef.current?.click()}
        type="button"
      >
        {isUploading ? "Uploading" : "Choose files"}
      </button>
    </section>
  );
}
