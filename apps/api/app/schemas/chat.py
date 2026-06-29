import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.conversation import MessageRole
from app.models.retrieval import RetrievalMode


class ChatRetrievalOptions(BaseModel):
    """Retrieval options for chat orchestration."""

    mode: RetrievalMode = RetrievalMode.hybrid
    top_k: int = Field(default=8, ge=1, le=50)
    vector_weight: float = Field(default=0.65, ge=0, le=1)
    keyword_weight: float = Field(default=0.35, ge=0, le=1)
    reranker_enabled: bool = False
    reranker_candidate_limit: int = Field(default=40, ge=1, le=200)

    @model_validator(mode="after")
    def validate_weights(self) -> "ChatRetrievalOptions":
        """Reject zero-total hybrid weights."""

        if self.mode == RetrievalMode.hybrid and self.vector_weight + self.keyword_weight <= 0:
            raise ValueError("hybrid weights must not both be zero")
        return self


class ChatMessageRequest(BaseModel):
    """Request body for sending a project-scoped chat message."""

    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1)
    retrieval: ChatRetrievalOptions = Field(default_factory=ChatRetrievalOptions)

    @model_validator(mode="after")
    def trim_message(self) -> "ChatMessageRequest":
        """Reject blank chat messages."""

        self.message = self.message.strip()
        if not self.message:
            raise ValueError("message must not be empty")
        return self


class ChatCitationRead(BaseModel):
    """Citation returned with a chat answer."""

    citation_index: int
    chunk_id: uuid.UUID
    quote: str | None
    citation_metadata: dict


class ChatMessageResponse(BaseModel):
    """Response body for a generated chat answer."""

    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    answer: str
    citations: list[ChatCitationRead]
    retrieval_log_id: uuid.UUID
    model: str
    latency_ms: int


class ConversationRead(BaseModel):
    """Project conversation summary."""

    id: uuid.UUID
    project_id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageRead(BaseModel):
    """Stored conversation message."""

    id: uuid.UUID
    project_id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    message_metadata: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailRead(ConversationRead):
    """Conversation with ordered messages."""

    messages: list[MessageRead]
