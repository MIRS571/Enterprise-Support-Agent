from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        extra="ignore",
    )

    app_name: str = "Enterprise Support Agent"
    app_version: str = "0.1.0"
    environment: str = "local"
    business_service_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8080")
    business_service_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
    )
    business_service_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
    )
    internal_service_token: SecretStr | None = Field(
        default=None,
        min_length=32,
    )
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_base_url: HttpUrl | None = None
    llm_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=120,
    )
    llm_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
    )
    llm_thinking_enabled: bool = False

    checkpoint_enabled: bool = False
    checkpoint_database_url: SecretStr | None = None

    redis_enabled: bool = False
    redis_url: SecretStr | None = None
    redis_socket_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        le=10,
    )
    redis_key_prefix: str = Field(
        default="esa",
        min_length=2,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    order_cache_ttl_seconds: int = Field(
        default=15,
        ge=1,
        le=300,
    )
    chat_rate_limit_requests: int = Field(
        default=10,
        ge=1,
        le=1000,
    )
    chat_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
    )

    qdrant_url: HttpUrl = HttpUrl("http://127.0.0.1:6333")
    qdrant_api_key: SecretStr | None = None
    qdrant_collection_name: str = "enterprise_support_knowledge_hybrid_v1"
    knowledge_base_directory: Path = Path("data/knowledge")
    rag_enabled: bool = True

    embedding_model_name: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    embedding_device: str = "cpu"
    embedding_normalize: bool = True
    sparse_embedding_model_name: str = "Qdrant/bm25"

    rag_candidate_k: int = Field(
        default=10,
        ge=2,
        le=100,
    )
    rag_reranker_enabled: bool = True
    rag_reranker_model_name: str = "BAAI/bge-reranker-base"
    rag_reranker_model_path: Path | None = None
    rag_reranker_batch_size: int = Field(
        default=8,
        ge=1,
        le=64,
    )

    rag_top_k: int = Field(
        default=3,
        ge=1,
        le=20,
    )
    rag_chunk_size: int = Field(
        default=500,
        ge=100,
        le=5000,
    )
    rag_chunk_overlap: int = Field(
        default=80,
        ge=0,
        le=1000,
    )

    @model_validator(mode="after")
    def validate_rag_chunking(self) -> Self:
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("rag_chunk_overlap must be smaller than rag_chunk_size")

        return self

    @model_validator(mode="after")
    def validate_rag_ranking(self) -> Self:
        if self.rag_candidate_k < self.rag_top_k:
            raise ValueError("rag_candidate_k must be at least rag_top_k")

        return self

    @model_validator(mode="after")
    def validate_checkpoint_configuration(self) -> Self:
        if self.checkpoint_enabled and self.checkpoint_database_url is None:
            raise ValueError(
                "checkpoint_database_url is required when checkpoint_enabled is true"
            )

        return self

    @model_validator(mode="after")
    def validate_redis_configuration(self) -> Self:
        if self.redis_enabled and self.redis_url is None:
            raise ValueError("redis_url is required when redis_enabled is true")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
