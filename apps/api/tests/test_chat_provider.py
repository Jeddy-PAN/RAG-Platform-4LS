import pytest

from app.rag.providers.chat import ChatProviderError, OpenAIChatProvider


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


def test_openai_chat_provider_request_shape() -> None:
    """Chat provider should call an OpenAI-compatible chat endpoint."""

    client = FakeHttpClient(
        FakeResponse(
            {
                "model": "chat-model",
                "choices": [{"message": {"content": "Answer from context"}}],
            }
        )
    )
    provider = OpenAIChatProvider(
        base_url="https://example.test/v1",
        api_key="secret",
        model="chat-model",
        client=client,
    )

    result = provider.generate_chat_completion(
        [{"role": "user", "content": "Question"}],
        temperature=0.1,
    )

    assert result.content == "Answer from context"
    assert result.model == "chat-model"
    assert client.calls[0][0] == "https://example.test/v1/chat/completions"
    assert client.calls[0][1]["json"]["model"] == "chat-model"
    assert client.calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_chat_provider_errors_are_clear() -> None:
    """Provider HTTP failures should become ChatProviderError."""

    provider = OpenAIChatProvider(
        base_url="https://example.test/v1",
        api_key="secret",
        model="chat-model",
        client=FakeHttpClient(FakeResponse({}, status_code=500)),
    )

    with pytest.raises(ChatProviderError, match="Chat API request failed"):
        provider.generate_chat_completion([{"role": "user", "content": "Question"}])


def test_chat_provider_error_includes_http_status() -> None:
    """Provider errors should include upstream status when available."""

    provider = OpenAIChatProvider(
        base_url="https://example.test/v1",
        api_key="secret",
        model="chat-model",
        client=FakeHttpClient(FakeResponse({}, status_code=402)),
    )

    with pytest.raises(ChatProviderError, match="402"):
        provider.generate_chat_completion([{"role": "user", "content": "Question"}])
