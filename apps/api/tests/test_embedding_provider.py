import pytest

from app.rag.providers.embeddings import EmbeddingProviderError, OpenAIEmbeddingProvider


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
