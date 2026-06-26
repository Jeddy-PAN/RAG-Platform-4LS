from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class ChatProviderError(RuntimeError):
    """Raised when a chat provider response is unusable."""


@dataclass(frozen=True)
class ChatProviderResult:
    """Normalized chat provider response."""

    content: str
    model: str


class OpenAIChatProvider:
    """OpenAI-compatible chat completions API client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=60.0)

    @classmethod
    def from_settings(cls) -> "OpenAIChatProvider":
        """Build the chat provider from application settings."""

        settings = get_settings()
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> ChatProviderResult:
        """Generate a non-streaming chat completion."""

        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code is None:
                status_code = getattr(response, "status_code", None) if "response" in locals() else None
            detail = f": {status_code}" if status_code else ""
            raise ChatProviderError(f"Chat API request failed{detail}") from exc

        return ChatProviderResult(content=content, model=payload.get("model", self.model))
