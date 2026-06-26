export type UUID = string;

export type Project = {
  id: UUID;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "indexed"
  | "failed";

export type DocumentItem = {
  id: UUID;
  project_id: UUID;
  filename: string;
  content_type: string | null;
  storage_path: string;
  file_size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type IngestionJob = {
  id: UUID;
  project_id: UUID;
  document_id: UUID;
  status: "queued" | "running" | "completed" | "failed";
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentUploadResponse = {
  document: DocumentItem;
  ingestion_job: IngestionJob;
};

export type RetrievalMode = "vector" | "keyword" | "hybrid";

export type ChatCitation = {
  citation_index: number;
  chunk_id: UUID;
  quote: string | null;
  citation_metadata: Record<string, unknown>;
};

export type ChatMessageResponse = {
  conversation_id: UUID;
  user_message_id: UUID;
  assistant_message_id: UUID;
  answer: string;
  citations: ChatCitation[];
  retrieval_log_id: UUID;
  model: string;
  latency_ms: number;
};

export type ChatMessage = {
  id: UUID;
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
  assistantMessageId?: UUID;
  latencyMs?: number;
  model?: string;
};

export type FeedbackRating = "positive" | "negative";

export type FeedbackResponse = {
  id: UUID;
  project_id: UUID;
  conversation_id: UUID;
  message_id: UUID;
  rating: FeedbackRating;
  comment: string | null;
  created_at: string;
  updated_at: string;
};

export type RetrievalResult = {
  rank: number;
  chunk_id: UUID;
  document_id: UUID;
  document_name: string;
  chunk_index: number;
  text_preview: string;
  source_metadata: Record<string, unknown>;
  vector_score: number | null;
  keyword_score: number | null;
  fused_score: number | null;
  score_metadata: Record<string, unknown>;
};

export type RetrievalResponse = {
  query: string;
  mode: RetrievalMode;
  top_k: number;
  latency_ms: number;
  results: RetrievalResult[];
  retrieval_log_id: UUID;
};

export type SystemConfig = {
  llm: {
    provider: string;
    base_url: string;
    model: string;
    api_key_configured: boolean;
  };
  embedding: {
    provider: string;
    base_url: string;
    model: string;
    dimensions: number;
    api_key_configured: boolean;
  };
};
