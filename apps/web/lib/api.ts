import type {
  ChatMessageResponse,
  DocumentItem,
  DocumentUploadResponse,
  EvalDataset,
  EvalQuestion,
  EvalRun,
  IngestionJob,
  FeedbackRating,
  FeedbackResponse,
  Project,
  RetrievalMode,
  RetrievalResponse,
  SystemConfig,
  UUID
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type JsonBody = Record<string, unknown>;

function buildUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const hasJson = contentType.includes("application/json");
  const payload = hasJson ? await response.json() : null;

  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload : undefined;
    const message =
      detail && "detail" in detail && typeof detail.detail === "string"
        ? detail.detail
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, detail);
  }

  return payload as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers
    }
  });

  return parseResponse<T>(response);
}

function jsonRequest<T>(path: string, method: string, body?: JsonBody): Promise<T> {
  return request<T>(path, {
    method,
    body: body ? JSON.stringify(body) : undefined
  });
}

export const projectsApi = {
  list: () => request<Project[]>("/api/projects"),
  create: (payload: { name: string; description?: string | null }) =>
    jsonRequest<Project>("/api/projects", "POST", payload),
  update: (projectId: UUID, payload: { name?: string; description?: string | null }) =>
    jsonRequest<Project>(`/api/projects/${projectId}`, "PATCH", payload),
  delete: async (projectId: UUID) => {
    await request<void>(`/api/projects/${projectId}`, { method: "DELETE" });
  }
};

export const documentsApi = {
  list: (projectId: UUID) => request<DocumentItem[]>(`/api/projects/${projectId}/documents`),
  upload: (projectId: UUID, file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    return request<DocumentUploadResponse>(`/api/projects/${projectId}/documents`, {
      method: "POST",
      body: formData
    });
  },
  delete: async (projectId: UUID, documentId: UUID) => {
    await request<void>(`/api/projects/${projectId}/documents/${documentId}`, {
      method: "DELETE"
    });
  },
  reindex: (projectId: UUID, documentId: UUID) =>
    request<IngestionJob>(`/api/projects/${projectId}/documents/${documentId}/reindex`, {
      method: "POST"
    })
};

export const chatApi = {
  sendMessage: (
    projectId: UUID,
    payload: {
      conversation_id: UUID | null;
      message: string;
      retrieval?: {
        mode: RetrievalMode;
        top_k: number;
        vector_weight: number;
        keyword_weight: number;
      };
    }
  ) => jsonRequest<ChatMessageResponse>(`/api/projects/${projectId}/chat/messages`, "POST", payload)
};

export const feedbackApi = {
  submit: (
    projectId: UUID,
    payload: {
      conversation_id: UUID;
      message_id: UUID;
      rating: FeedbackRating;
      comment?: string | null;
    }
  ) => jsonRequest<FeedbackResponse>(`/api/projects/${projectId}/feedback`, "POST", payload)
};

export const retrievalApi = {
  query: (
    projectId: UUID,
    payload: {
      query: string;
      mode: RetrievalMode;
      top_k: number;
      vector_weight: number;
      keyword_weight: number;
      similarity_threshold: number;
    }
  ) => jsonRequest<RetrievalResponse>(`/api/projects/${projectId}/retrieval/query`, "POST", payload)
};

export const evalApi = {
  listDatasets: (projectId: UUID) =>
    request<EvalDataset[]>(`/api/projects/${projectId}/eval/datasets`),
  createDataset: (
    projectId: UUID,
    payload: { name: string; description?: string | null }
  ) => jsonRequest<EvalDataset>(`/api/projects/${projectId}/eval/datasets`, "POST", payload),
  createQuestion: (
    projectId: UUID,
    datasetId: UUID,
    payload: {
      question: string;
      expected_document_id?: UUID | null;
      expected_chunk_id?: UUID | null;
      expected_answer_notes?: string | null;
      should_answer?: boolean;
    }
  ) =>
    jsonRequest<EvalQuestion>(
      `/api/projects/${projectId}/eval/datasets/${datasetId}/questions`,
      "POST",
      payload
    ),
  runDataset: (
    projectId: UUID,
    datasetId: UUID,
    payload: {
      retrieval_mode: RetrievalMode;
      top_k: number;
      vector_weight: number;
      keyword_weight: number;
    }
  ) =>
    jsonRequest<EvalRun>(
      `/api/projects/${projectId}/eval/datasets/${datasetId}/runs`,
      "POST",
      payload
    )
};

export const systemApi = {
  config: () => request<SystemConfig>("/api/system/config")
};
