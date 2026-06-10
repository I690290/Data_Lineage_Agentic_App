"""Application settings loaded from environment / .env using pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application configuration, sourced from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""
    aws_region: str = "us-east-1"
    aws_profile: str = "default"

    # Bedrock models
    bedrock_model_id: str = "qwen.qwen3-coder-next"
    bedrock_text_model_id: str = "amazon.nova-pro-v1:0"
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "lineage_password"

    # ChromaDB (in-process persistent storage)
    chromadb_persist_dir: str = "./data/chromadb"
    chroma_persist_dir: str = "./chroma_db"  # legacy alias
    chromadb_host: str = ""
    chromadb_port: int = 8000

    # OpenTelemetry / Jaeger (local)
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "data-lineage-agent"
    enable_tracing: bool = True

    # FastAPI
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # Application
    repo_path: str = "./mock_code"
    mock_code_dir: str = "./mock_code"
    output_dir: str = "./output"
    hash_cache_path: str = "./hash_cache.db"
    lineage_json_path: str = "./lineage_output.json"
    log_level: str = "INFO"

    # Agent behaviour
    max_chunk_tokens: int = 4096
    chroma_top_k: int = 5
    reflexion_max_retries: int = 3
    min_confidence_threshold: float = 0.1


settings = Settings()
