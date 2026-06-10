"""FastAPI application — data lineage visualisation and extraction API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import evaluation, extraction, lineage, rag
from src.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure OTel tracing on startup."""
    if settings.enable_tracing:
        from observability.tracing import setup_tracing
        setup_tracing(
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        )
    yield


app = FastAPI(
    title="Data Lineage Agent API",
    description="Agentic AI data lineage extraction for COBOL/Java/SQL codebases.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(lineage.router, prefix="/api/lineage", tags=["lineage"])
app.include_router(extraction.router, prefix="/api/lineage", tags=["extraction"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(evaluation.router, prefix="/api/eval", tags=["evaluation"])


@app.get("/api/health")
async def health_check() -> dict:
    """Health check — verifies Neo4j, ChromaDB, and Bedrock connectivity."""
    status: dict = {"status": "ok", "services": {}}

    # Neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session() as s:
            s.run("RETURN 1")
        driver.close()
        status["services"]["neo4j"] = "ok"
    except Exception as exc:
        status["services"]["neo4j"] = f"error: {exc}"
        status["status"] = "degraded"

    # ChromaDB
    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        client.list_collections()
        status["services"]["chromadb"] = "ok"
    except Exception as exc:
        status["services"]["chromadb"] = f"error: {exc}"
        status["status"] = "degraded"

    # Bedrock (ping only)
    try:
        import boto3
        bedrock = boto3.client("bedrock", region_name=settings.aws_region)
        bedrock.list_foundation_models(byOutputModality="TEXT")
        status["services"]["bedrock"] = "ok"
    except Exception as exc:
        status["services"]["bedrock"] = f"error: {exc}"

    return status
