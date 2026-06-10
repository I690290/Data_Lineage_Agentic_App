"""
LangGraph tools available to the code_analysis_node ReAct agent:
  - search_codebase: semantic search over ChromaDB code_chunks
  - get_file_content: return raw file content by path
  - resolve_config_key: look up a datasource/config key from config_mappings
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import boto3
import chromadb
from langchain_core.tools import tool

from src.ingest import TitanEmbeddingFunction as _TitanEmbed
from src.config import settings


def _get_collections():
    embed_fn = _TitanEmbed()
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    code_col = client.get_or_create_collection(
        name="code_chunks",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    config_col = client.get_or_create_collection(
        name="config_mappings",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return code_col, config_col


# Lazy-initialised singletons (avoid re-connecting on every tool call)
_code_col = None
_config_col = None


def _collections():
    global _code_col, _config_col
    if _code_col is None or _config_col is None:
        _code_col, _config_col = _get_collections()
    return _code_col, _config_col


@tool
def search_codebase(
    query: Annotated[str, "Natural language query to search the codebase"],
    language: Annotated[str, "Filter by language: cobol | java | jcl | config | '' for all"] = "",
    top_k: Annotated[int, "Number of results to return"] = 5,
) -> str:
    """
    Semantic search over all ingested code chunks using Titan Embeddings.
    Returns JSON list of matching chunks with file_path, chunk_type, chunk_name, and content snippet.
    """
    code_col, _ = _collections()
    where = {"language": language} if language else None
    try:
        results = code_col.query(
            query_texts=[query],
            n_results=min(top_k, 10),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        items = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            items.append({
                "file_path": meta.get("file_path", ""),
                "language": meta.get("language", ""),
                "chunk_type": meta.get("chunk_type", ""),
                "chunk_name": meta.get("chunk_name", ""),
                "relevance_score": round(1 - dist, 4),
                "content_snippet": doc[:500] + ("..." if len(doc) > 500 else ""),
                "metadata": {k: v for k, v in meta.items()
                             if k not in ("file_path", "language", "chunk_type", "chunk_name")},
            })
        return json.dumps(items, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
def get_file_content(
    file_path: Annotated[str, "Absolute or relative path to the source file"],
) -> str:
    """
    Return the full raw content of a source file.
    Use when you need the complete file rather than a search result snippet.
    """
    try:
        p = Path(file_path)
        if not p.exists():
            # Try relative to repo_path
            p = Path(settings.repo_path) / file_path
        if not p.exists():
            return json.dumps({"error": f"File not found: {file_path}"})
        content = p.read_text(encoding="utf-8", errors="replace")
        return json.dumps({"file_path": str(p), "content": content})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
def resolve_config_key(
    key: Annotated[str, "Config key to resolve, e.g. 'spring.datasource.customer.schema' or datasource bean name"],
) -> str:
    """
    Look up a Spring datasource / config key and return the resolved value
    (e.g. the actual schema name or table name it maps to).
    Searches the config_mappings ChromaDB collection.
    """
    _, config_col = _collections()
    try:
        results = config_col.query(
            query_texts=[key],
            n_results=3,
            include=["documents", "metadatas"],
        )
        items = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            items.append({
                "file_path": meta.get("file_path", ""),
                "config_key_hint": key,
                "content_snippet": doc[:400],
            })
        return json.dumps(items, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


LINEAGE_TOOLS = [search_codebase, get_file_content, resolve_config_key]
