"""HTTP client for FastAPI backend communication."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from streamlit_app.config import FASTAPI_BASE_URL


class APIClientError(Exception):
    """Raised when the FastAPI backend returns a non-200 response."""


@dataclass
class RagAnswer:
    """Structured response returned by the RAG backend."""

    answer: str
    citations: list[dict[str, Any]]


class LineageAPIClient:
    """Wrap all FastAPI backend calls with consistent error handling."""

    def __init__(self, base_url: str = FASTAPI_BASE_URL) -> None:
        """Initialise the API client."""
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(60.0)

    def _get(self, path: str) -> Any:
        """Issue a GET request and decode JSON."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(f"{self._base_url}{path}")
        if response.status_code != 200:
            raise APIClientError(
                f"GET {path} returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    def get_summary(self) -> dict[str, Any]:
        """Fetch lineage summary counts from the API."""
        return self._get("/api/lineage/summary")

    def get_history(self) -> list[dict[str, Any]]:
        """Fetch recent RAG history entries."""
        return self._get("/api/rag/history")

    def delete_history(self) -> None:
        """Clear all RAG history."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.delete(f"{self._base_url}/api/rag/history")
        if response.status_code != 200:
            raise APIClientError(f"DELETE /api/rag/history returned {response.status_code}")

    def ask_sync(self, question: str, max_chunks: int = 8, history: list[dict] | None = None) -> RagAnswer:
        """Send a non-streaming RAG query."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/api/rag/ask",
                json={
                    "question": question,
                    "stream": False,
                    "max_chunks": max_chunks,
                    "history": history or [],
                },
            )
        if response.status_code != 200:
            raise APIClientError(
                f"POST /api/rag/ask returned {response.status_code}: {response.text[:200]}"
            )
        data = response.json()
        return RagAnswer(answer=data.get("answer", ""), citations=data.get("citations", []))
