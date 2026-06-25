import httpx

from app.core.config import get_settings


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider response is unusable."""


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embeddings API client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        client=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.client = client or httpx.Client(timeout=30.0)

    @classmethod
    def from_settings(cls) -> "OpenAIEmbeddingProvider":
        """Build the provider from application settings."""

        settings = get_settings()
        return cls(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts and validate response count and dimensions."""

        if not texts:
            return []
        try:
            response = self.client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise EmbeddingProviderError("Embedding API request failed") from exc

        vectors = [item.get("embedding") for item in payload.get("data", [])]
        if len(vectors) != len(texts):
            raise EmbeddingProviderError("Embedding response count mismatch")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise EmbeddingProviderError("Embedding dimension mismatch")
        return vectors
