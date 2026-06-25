import httpx

from app.core.config import Settings, get_settings
from app.rag.providers.types import EmbeddingProvider


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
    def from_settings(cls, settings: Settings | None = None) -> "OpenAIEmbeddingProvider":
        """Build the provider from application settings."""

        settings = settings or get_settings()
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

        return _validate_vectors(
            [item.get("embedding") for item in payload.get("data", [])],
            expected_count=len(texts),
            expected_dimensions=self.dimensions,
        )


class OllamaEmbeddingProvider:
    """Ollama local embeddings API client."""

    def __init__(
        self,
        base_url: str,
        model: str,
        dimensions: int,
        client=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.client = client or httpx.Client(timeout=60.0)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OllamaEmbeddingProvider":
        """Build the provider from application settings."""

        settings = settings or get_settings()
        return cls(
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with Ollama and validate response count and dimensions."""

        if not texts:
            return []
        try:
            response = self.client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise EmbeddingProviderError("Ollama embedding request failed") from exc

        return _validate_vectors(
            payload.get("embeddings", []),
            expected_count=len(texts),
            expected_dimensions=self.dimensions,
        )


def get_embedding_provider_from_settings(
    settings: Settings | None = None,
) -> EmbeddingProvider:
    """Build the configured embedding provider."""

    settings = settings or get_settings()
    provider = settings.embedding_provider.strip().lower()
    if provider in {"openai_compatible", "openai"}:
        return OpenAIEmbeddingProvider.from_settings(settings)
    if provider in {"ollama", "local_ollama"}:
        return OllamaEmbeddingProvider.from_settings(settings)
    raise EmbeddingProviderError(f"Unsupported embedding provider: {settings.embedding_provider}")


def _validate_vectors(
    vectors: list,
    expected_count: int,
    expected_dimensions: int,
) -> list[list[float]]:
    """Validate provider vectors before storing or searching with them."""

    if len(vectors) != expected_count:
        raise EmbeddingProviderError("Embedding response count mismatch")
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != expected_dimensions:
            raise EmbeddingProviderError("Embedding dimension mismatch")
    return vectors
