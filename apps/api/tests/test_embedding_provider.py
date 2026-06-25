import pytest

from app.core.config import Settings
from app.rag.providers.embeddings import (
    EmbeddingProviderError,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider_from_settings,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("api error")

    def json(self) -> dict:
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_openai_embedding_provider_request_shape() -> None:
    """Embedding provider should call the OpenAI-compatible endpoint."""

    client = FakeHttpClient(
        FakeResponse(
            {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
        )
    )
    provider = OpenAIEmbeddingProvider(
        base_url="https://example.test/v1",
        api_key="secret",
        model="embed-small",
        dimensions=2,
        client=client,
    )

    vectors = provider.embed_texts(["alpha", "beta"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert client.calls[0][0] == "https://example.test/v1/embeddings"
    assert client.calls[0][1]["json"] == {
        "model": "embed-small",
        "input": ["alpha", "beta"],
    }
    assert client.calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_embedding_provider_rejects_dimension_mismatch() -> None:
    """Embedding provider should fail clearly when dimensions are wrong."""

    client = FakeHttpClient(FakeResponse({"data": [{"embedding": [0.1]}]}))
    provider = OpenAIEmbeddingProvider(
        base_url="https://example.test/v1",
        api_key="secret",
        model="embed-small",
        dimensions=2,
        client=client,
    )

    with pytest.raises(EmbeddingProviderError, match="dimension"):
        provider.embed_texts(["alpha"])


def test_embedding_provider_rejects_count_mismatch() -> None:
    """Embedding provider should validate response count against input count."""

    client = FakeHttpClient(FakeResponse({"data": [{"embedding": [0.1, 0.2]}]}))
    provider = OpenAIEmbeddingProvider(
        base_url="https://example.test/v1",
        api_key="secret",
        model="embed-small",
        dimensions=2,
        client=client,
    )

    with pytest.raises(EmbeddingProviderError, match="count"):
        provider.embed_texts(["alpha", "beta"])


def test_ollama_embedding_provider_request_shape() -> None:
    """Ollama provider should call the local embed endpoint."""

    client = FakeHttpClient(FakeResponse({"embeddings": [[0.1, 0.2], [0.3, 0.4]]}))
    provider = OllamaEmbeddingProvider(
        base_url="http://localhost:11434",
        model="bge-m3",
        dimensions=2,
        client=client,
    )

    vectors = provider.embed_texts(["alpha", "beta"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert client.calls[0][0] == "http://localhost:11434/api/embed"
    assert client.calls[0][1]["json"] == {
        "model": "bge-m3",
        "input": ["alpha", "beta"],
    }
    assert "headers" not in client.calls[0][1]


def test_ollama_embedding_provider_rejects_dimension_mismatch() -> None:
    """Ollama provider should fail clearly when dimensions are wrong."""

    client = FakeHttpClient(FakeResponse({"embeddings": [[0.1]]}))
    provider = OllamaEmbeddingProvider(
        base_url="http://localhost:11434",
        model="bge-m3",
        dimensions=2,
        client=client,
    )

    with pytest.raises(EmbeddingProviderError, match="dimension"):
        provider.embed_texts(["alpha"])


def test_embedding_provider_factory_selects_openai_compatible() -> None:
    """Factory should keep the cloud embedding provider as a supported option."""

    settings = Settings(
        embedding_provider="openai_compatible",
        embedding_base_url="https://example.test/v1",
        embedding_api_key="secret",
        embedding_model="embed-small",
        embedding_dimensions=2,
    )

    provider = get_embedding_provider_from_settings(settings)

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.base_url == "https://example.test/v1"
    assert provider.model == "embed-small"


def test_embedding_provider_factory_selects_ollama() -> None:
    """Factory should build the local Ollama embedding provider."""

    settings = Settings(
        embedding_provider="ollama",
        embedding_base_url="http://localhost:11434",
        embedding_model="bge-m3",
        embedding_dimensions=1024,
    )

    provider = get_embedding_provider_from_settings(settings)

    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "bge-m3"


def test_embedding_provider_factory_rejects_unknown_provider() -> None:
    """Factory should fail clearly for unsupported embedding providers."""

    settings = Settings(embedding_provider="unknown")

    with pytest.raises(EmbeddingProviderError, match="Unsupported embedding provider"):
        get_embedding_provider_from_settings(settings)
