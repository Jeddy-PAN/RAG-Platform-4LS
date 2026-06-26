from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings


router = APIRouter(prefix="/api/system", tags=["system"])


class LLMConfigRead(BaseModel):
    """Safe-to-display chat provider configuration."""

    provider: str
    base_url: str
    model: str
    api_key_configured: bool


class EmbeddingConfigRead(BaseModel):
    """Safe-to-display embedding provider configuration."""

    provider: str
    base_url: str
    model: str
    dimensions: int
    api_key_configured: bool


class SystemConfigRead(BaseModel):
    """Safe-to-display runtime model provider configuration."""

    llm: LLMConfigRead
    embedding: EmbeddingConfigRead


@router.get("/config", response_model=SystemConfigRead)
def get_system_config() -> SystemConfigRead:
    """Return provider settings without exposing secrets."""

    settings = get_settings()
    return SystemConfigRead(
        llm=LLMConfigRead(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key_configured=bool(settings.llm_api_key),
        ),
        embedding=EmbeddingConfigRead(
            provider=settings.embedding_provider,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            api_key_configured=bool(settings.embedding_api_key),
        ),
    )
