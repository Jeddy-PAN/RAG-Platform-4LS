import httpx
import math
import pytest

from app.core.config import Settings
from app.rag.providers.reranking import (
    OpenAICompatibleRerankerProvider,
    get_reranker_provider_from_settings,
)
from app.rag.retrieval.rerankers import RerankerProviderError, RerankerTransportError
from app.rag.retrieval.types import RetrievalCandidate
import uuid


def _candidate(text: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="synthetic.txt",
        chunk_index=0,
        text=text,
        source_metadata={},
    )


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, *, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if self.error:
            raise self.error
        return self.response


def _response(body, status_code=200):
    return httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("POST", "http://reranker.test/rerank"),
    )


def test_http_provider_sends_bounded_multilingual_payload_without_logging() -> None:
    client = FakeClient(_response({"scores": [0.2, 0.9]}))
    provider = OpenAICompatibleRerankerProvider(
        base_url="http://reranker.test/v1",
        api_key="synthetic-secret",
        model="multilingual-cross-encoder",
        timeout_seconds=2.5,
        http_client=client,
    )
    candidates = [_candidate("服务器用户名"), _candidate("login credentials")]

    assert provider.score("请查找 login credentials", candidates) == [0.2, 0.9]
    url, body, headers, timeout = client.calls[0]
    assert url == "http://reranker.test/v1/rerank"
    assert body["model"] == "multilingual-cross-encoder"
    assert body["documents"] == [candidate.text for candidate in candidates]
    assert headers["Authorization"] == "Bearer synthetic-secret"
    assert timeout == 2.5


@pytest.mark.parametrize(
    "body",
    [{"scores": [0.2]}, {"scores": ["bad", 0.9]}, {"scores": [float("nan"), 0.9]}],
)
def test_http_provider_rejects_invalid_score_responses(body) -> None:
    class JsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return body

    provider = OpenAICompatibleRerankerProvider(
        base_url="http://reranker.test",
        api_key="",
        model="synthetic",
        timeout_seconds=1,
        http_client=FakeClient(JsonResponse()),
    )

    with pytest.raises(RerankerProviderError):
        provider.score("query", [_candidate("a"), _candidate("b")])


def test_http_provider_maps_timeout_and_status_to_transport_failure() -> None:
    timeout_provider = OpenAICompatibleRerankerProvider(
        base_url="http://reranker.test",
        api_key="",
        model="synthetic",
        timeout_seconds=1,
        http_client=FakeClient(error=httpx.ReadTimeout("timeout")),
    )
    with pytest.raises(RerankerTransportError):
        timeout_provider.score("query", [_candidate("a")])

    status_provider = OpenAICompatibleRerankerProvider(
        base_url="http://reranker.test",
        api_key="",
        model="synthetic",
        timeout_seconds=1,
        http_client=FakeClient(_response({}, status_code=503)),
    )
    with pytest.raises(RerankerTransportError):
        status_provider.score("query", [_candidate("a")])


def test_reranker_factory_selects_safe_configured_provider() -> None:
    assert get_reranker_provider_from_settings(Settings(reranker_provider="disabled")) is None
    assert (
        get_reranker_provider_from_settings(
            Settings(reranker_provider="disabled", reranker_timeout_seconds=math.nan)
        )
        is None
    )
    assert get_reranker_provider_from_settings(Settings(reranker_provider="keyword_overlap")).name == "keyword_overlap"
    with pytest.raises(RerankerProviderError, match="configuration_invalid"):
        get_reranker_provider_from_settings(
            Settings(reranker_provider="multilingual_cross_encoder")
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"reranker_provider": "unsupported"},
        {"reranker_provider": "keyword_overlap", "reranker_timeout_seconds": 0},
        {"reranker_provider": "keyword_overlap", "reranker_candidate_limit": 0},
        {
            "reranker_provider": "multilingual_cross_encoder",
            "reranker_base_url": "http://reranker.test",
            "reranker_model": "synthetic",
            "reranker_timeout_seconds": 0,
        },
        {
            "reranker_provider": "multilingual_cross_encoder",
            "reranker_base_url": "http://reranker.test",
            "reranker_model": "synthetic",
            "reranker_timeout_seconds": math.nan,
        },
        {
            "reranker_provider": "multilingual_cross_encoder",
            "reranker_base_url": "http://reranker.test",
            "reranker_model": "synthetic",
            "reranker_timeout_seconds": math.inf,
        },
        {
            "reranker_provider": "multilingual_cross_encoder",
            "reranker_base_url": "http://reranker.test",
            "reranker_model": "synthetic",
            "reranker_timeout_seconds": -math.inf,
        },
    ],
)
def test_reranker_factory_rejects_invalid_configuration(overrides) -> None:
    with pytest.raises(RerankerProviderError, match="configuration_invalid"):
        get_reranker_provider_from_settings(Settings(**overrides))
