"""Application settings loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from config.models import BedrockModels

load_dotenv()


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    aws_access_key_id: str = field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", ""))
    aws_secret_access_key: str = field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", ""))
    aws_session_token: str = field(default_factory=lambda: os.getenv("AWS_SESSION_TOKEN", ""))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    bedrock_embed_model_id: str = field(
        default_factory=lambda: os.getenv(
            "BEDROCK_EMBED_MODEL_ID", BedrockModels.TITAN_EMBED_V2
        )
    )
    bedrock_text_model_id: str = field(
        default_factory=lambda: os.getenv(
            "BEDROCK_TEXT_MODEL_ID", BedrockModels.NOVA_PRO
        )
    )
    repo_path: str = field(default_factory=lambda: os.getenv("REPO_PATH", "./mock_code"))
    chroma_persist_dir: str = field(
        default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    )
    hash_cache_path: str = field(
        default_factory=lambda: os.getenv("HASH_CACHE_PATH", "./hash_cache.db")
    )
    neo4j_uri: str = field(
        default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))
    lineage_json_path: str = field(
        default_factory=lambda: os.getenv("LINEAGE_JSON_PATH", "./lineage_output.json")
    )
    max_chunk_tokens: int = 4096
    chroma_top_k: int = 5
    # OpenTelemetry / Jaeger tracing (optional — disabled by default)
    enable_tracing: bool = field(
        default_factory=lambda: os.getenv("ENABLE_TRACING", "false").lower() == "true"
    )
    otel_service_name: str = field(
        default_factory=lambda: os.getenv("OTEL_SERVICE_NAME", "data-lineage-agent")
    )
    otel_exporter_otlp_endpoint: str = field(
        default_factory=lambda: os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    )

    def validate(self) -> None:
        """Validate required settings before running live workflows."""
        if not self.aws_access_key_id:
            raise ValueError("AWS_ACCESS_KEY_ID is required. Set it in your .env file.")
        if not self.aws_secret_access_key:
            raise ValueError("AWS_SECRET_ACCESS_KEY is required. Set it in your .env file.")
        if not self.neo4j_password:
            raise ValueError("NEO4J_PASSWORD is required. Set it in your .env file.")
        if not Path(self.repo_path).exists():
            raise ValueError(f"REPO_PATH does not exist: {self.repo_path}")


settings = Settings()
