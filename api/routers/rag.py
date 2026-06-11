"""Agentic RAG query endpoints."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()
_rag_agent = None

# In-memory conversation history (survives for the lifetime of the process)
_history: list[dict[str, Any]] = []


def _get_rag() -> Any:
    global _rag_agent
    if _rag_agent is None:
        from rag.strands_rag import StrandsRAG
        _rag_agent = StrandsRAG()
    return _rag_agent


def _fetch_citations(question: str, max_chunks: int) -> list[dict[str, Any]]:
    """Run a ChromaDB vector search and return formatted citation dicts."""
    try:
        import chromadb
        from src.config import settings
        from src.ingest import TitanEmbeddingFunction

        embed_fn = TitanEmbeddingFunction()
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = client.get_or_create_collection(
            name="code_chunks",
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        results = collection.query(
            query_texts=[question],
            n_results=min(max_chunks, 10),
            include=["documents", "metadatas", "distances"],
        )
        citations = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            citations.append({
                "source_file":     meta.get("file_path", ""),
                "chunk_type":      meta.get("chunk_type", "code"),
                "key":             f"[{len(citations) + 1}]",
                "language":        meta.get("language", ""),
                "relevance_score": round(1 - dist, 4),
                "snippet":         doc[:400],
            })
        return citations
    except Exception:
        return []


class RAGQuery(BaseModel):
    question: str


class AskRequest(BaseModel):
    question: str
    stream: bool = False
    max_chunks: int = 8
    history: list[dict[str, Any]] = []


@router.post("/query")
async def rag_query(query: RAGQuery) -> dict[str, Any]:
    """Answer a natural-language lineage question using the Strands RAG agent."""
    try:
        rag = _get_rag()
        answer = rag.query(query.question)
        return {"question": query.question, "answer": answer}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ask")
async def rag_ask(request: AskRequest) -> Any:
    """Answer a lineage question with optional SSE streaming.

    - ``stream=false``: returns ``{"answer": "...", "citations": [...]}``
    - ``stream=true``: returns an SSE stream of tokens followed by a
      ``event: citations`` frame containing the citation JSON array.
    """
    try:
        rag = _get_rag()
        answer = rag.query(request.question, history=request.history)
        citations = _fetch_citations(request.question, request.max_chunks)

        entry: dict[str, Any] = {
            "id":        str(uuid.uuid4())[:8],
            "question":  request.question,
            "answer":    answer,
            "citations": citations,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _history.append(entry)
        # Keep last 100 entries in memory
        if len(_history) > 100:
            _history.pop(0)

        if not request.stream:
            return {"answer": answer, "citations": citations}

        # SSE streaming — yield answer word-by-word then citations frame
        def _event_stream():
            for word in answer.split(" "):
                yield f"data: {word} \n\n"
            citations_json = json.dumps(citations)
            yield f"event: citations\ndata: {citations_json}\n\n"

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
async def get_history() -> list[dict[str, Any]]:
    """Return the most recent 50 RAG conversation entries."""
    return list(reversed(_history))[:50]


@router.delete("/history")
async def delete_history() -> dict[str, str]:
    """Clear all in-memory RAG conversation history."""
    _history.clear()
    return {"status": "cleared"}

