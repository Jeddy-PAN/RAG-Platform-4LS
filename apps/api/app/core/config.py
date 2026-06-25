from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Local Enterprise RAG Platform")
    environment: str = Field(default="local")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    database_url: str = Field(
        default="postgresql+psycopg://rag:rag@postgres:5432/rag"
    )
    redis_url: str = Field(default="redis://redis:6379/0")
    rq_queue_name: str = Field(default="default")

    llm_provider: str = Field(default="openai_compatible")
    llm_base_url: str = Field(default="https://api.example.com/v1")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="example-chat-model")

    embedding_provider: str = Field(default="openai_compatible")
    embedding_base_url: str = Field(default="https://api.example.com/v1")
    embedding_api_key: str = Field(default="")
    embedding_model: str = Field(default="example-embedding-model")
    embedding_dimensions: int = Field(default=1024)

    upload_storage_dir: str = Field(default="data/uploads")
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
