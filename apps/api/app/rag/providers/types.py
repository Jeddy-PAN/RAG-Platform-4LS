from typing import Protocol


class ChatProvider(Protocol):
    """Protocol for chat completion providers."""

    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ):
        """Return a generated chat answer."""


class EmbeddingProvider(Protocol):
    """Protocol for embedding text batches."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
