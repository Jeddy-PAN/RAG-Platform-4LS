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

export type EvalDataset = {
  id: UUID;
  project_id: UUID;
  name: string;
  description: string | null;
  question_count: number;
  created_at: string;
  updated_at: string;
};

export type EvalQuestion = {
  id: UUID;
  project_id: UUID;
  dataset_id: UUID;
  question: string;
  expected_document_id: UUID | null;
  expected_chunk_id: UUID | null;
  expected_answer_notes: string | null;
  should_answer: boolean;
  created_at: string;
  updated_at: string;
};

export type EvalResult = {
  id: UUID;
  question_id: UUID;
  question: string;
  answer: string | null;
  hit: boolean;
  citation_covered: boolean;
  refused: boolean;
  answer_matched: boolean;
  retrieval_latency_ms: number | null;
  generation_latency_ms: number | null;
  score: number | null;
  result_metadata: Record<string, unknown>;
};

export type EvalRun = {
  id: UUID;
  project_id: UUID;
  dataset_id: UUID;
  status: "queued" | "running" | "completed" | "failed";
  retrieval_mode: RetrievalMode;
  top_k: number;
  metrics: Record<string, number>;
  error_message: string | null;
  results: EvalResult[];
  created_at: string;
  updated_at: string;
};

export type EvalRunSummary = Omit<EvalRun, "results"> & {
  result_count: number;
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
