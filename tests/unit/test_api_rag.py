"""Unit tests for RAG FastAPI endpoints."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client."""
    with patch("src.neo4j_writer.GraphDatabase"), patch(
        "src.api.fetch_full_lineage", return_value={"nodes": [], "edges": []}
    ):
        from src.api import app

        return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    """GET /health should return 200 ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rag_ask_missing_question(client: TestClient) -> None:
    """POST /rag/ask without question should return 400."""
    with patch("src.api._get_rag_components"):
        response = client.post("/rag/ask", json={"question": "", "stream": False})
    assert response.status_code == 400


def test_rag_history_empty(client: TestClient) -> None:
    """GET /rag/history should return a list when no history exists."""
    response = client.get("/rag/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_rag_history_delete(client: TestClient) -> None:
    """DELETE /rag/history should clear history."""
    response = client.delete("/rag/history")
    assert response.status_code == 200
    assert response.json().get("status") == "cleared"
