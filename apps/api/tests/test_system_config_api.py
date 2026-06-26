from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_system_config_summarizes_provider_settings_without_secrets(monkeypatch) -> None:
    """System config should expose provider readiness without leaking API keys."""

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/api/system/config")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "llm": {
            "provider": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key_configured": True,
        },
        "embedding": {
            "provider": "ollama",
            "base_url": "http://host.docker.internal:11434",
            "model": "bge-m3",
            "dimensions": 1024,
            "api_key_configured": False,
        },
    }
    assert "secret-key" not in response.text
    get_settings.cache_clear()
