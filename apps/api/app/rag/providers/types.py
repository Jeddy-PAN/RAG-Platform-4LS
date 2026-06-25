from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding text batches."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
