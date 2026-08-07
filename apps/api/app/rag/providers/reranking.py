"""Optional OpenAI-compatible multilingual reranker provider."""

from collections.abc import Sequence
import math

import httpx

from app.core.config import Settings, get_settings
from app.rag.retrieval.rerankers import (
    RerankerProviderError,
    RerankerTransportError,
    validate_reranker_scores,
)
from app.rag.retrieval.types import RetrievalCandidate


def _validate_timeout(timeout_seconds: object) -> float:
    try:
        value = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise RerankerProviderError("configuration_invalid") from exc
    if not math.isfinite(value) or value <= 0:
        raise RerankerProviderError("configuration_invalid")
    return value


class OpenAICompatibleRerankerProvider:
    name = "multilingual_cross_encoder"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not model:
            raise RerankerProviderError("configuration_invalid")
        timeout_seconds = _validate_timeout(timeout_seconds)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def score(self, query: str, candidates: list[RetrievalCandidate]) -> list[float]:
        payload = {
            "model": self.model,
            "query": query,
            "documents": [candidate.search_text or candidate.text for candidate in candidates],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self.http_client.post(
                f"{self.base_url}/rerank",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RerankerTransportError("provider_unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise RerankerTransportError("provider_unavailable") from exc
        except (ValueError, TypeError) as exc:
            raise RerankerProviderError("response_invalid") from exc

        if not isinstance(body, dict) or not isinstance(body.get("scores"), Sequence):
            raise RerankerProviderError("response_invalid")
        return validate_reranker_scores(body["scores"], len(candidates))


def get_reranker_provider_from_settings(
    settings: Settings | None = None,
):
    """Construct the configured provider without making a network request."""

    configured = settings or get_settings()
    provider_name = configured.reranker_provider
    if provider_name == "disabled":
        return None
    try:
        timeout = _validate_timeout(configured.reranker_timeout_seconds)
        candidate_limit = int(configured.reranker_candidate_limit)
    except (RerankerProviderError, TypeError, ValueError) as exc:
        if isinstance(exc, RerankerProviderError):
            raise
        raise RerankerProviderError("configuration_invalid") from exc
    if isinstance(configured.reranker_candidate_limit, bool) or candidate_limit <= 0:
        raise RerankerProviderError("configuration_invalid")
    if provider_name == "keyword_overlap":
        from app.rag.retrieval.rerankers import KeywordOverlapReranker

        return KeywordOverlapReranker()
    if provider_name != "multilingual_cross_encoder":
        raise RerankerProviderError("configuration_invalid")
    if not configured.reranker_base_url or not configured.reranker_model:
        raise RerankerProviderError("configuration_invalid")
    return OpenAICompatibleRerankerProvider(
        base_url=configured.reranker_base_url,
        api_key=configured.reranker_api_key,
        model=configured.reranker_model,
        timeout_seconds=timeout,
    )
