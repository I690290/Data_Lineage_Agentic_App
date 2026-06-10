"""Vector search tool — semantic search over ChromaDB."""
from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool


@tool
def vector_search_tool(
    query: Annotated[str, "Natural language query to find related code chunks"],
    language: Annotated[str, "Filter by language: COBOL | Java | SQL | JCL | '' for all"] = "",
    top_k: Annotated[int, "Number of results to return (max 10)"] = 5,
) -> str:
    """Semantic search over all ingested code chunks in ChromaDB.

    Returns JSON list of matching chunks with file_path, ast_path, content snippet.
    Use to find related code across files for cross-language lineage tracing.
    """
    import chromadb

    from src.config import settings
    from src.ingest import TitanEmbeddingFunction

    try:
        embed_fn = TitanEmbeddingFunction()
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = client.get_or_create_collection(
            name="code_chunks",
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        where = {"language": language} if language else None
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, 10),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        items: list[dict[str, Any]] = []
        for document, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            items.append(
                {
                    "file_path": metadata.get("file_path", ""),
                    "language": metadata.get("language", ""),
                    "ast_path": metadata.get("ast_path", metadata.get("chunk_type", "")),
                    "structural_type": metadata.get("structural_type", ""),
                    "relevance_score": round(1 - distance, 4),
                    "content_snippet": document[:600],
                }
            )
        return json.dumps(items, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
