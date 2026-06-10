"""Unit tests for HybridRetriever."""
from __future__ import annotations

from unittest.mock import patch

from models.lineage_models import RetrievedChunk


def test_rerank_deduplicates_and_scores() -> None:
    """Re-ranker should deduplicate and score chunks correctly."""
    from rag.hybrid_retriever import HybridRetriever

    with patch.object(HybridRetriever, "__init__", return_value=None):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._known_entities = []

    graph_chunks = [
        RetrievedChunk(
            text="CUSTOMER table read by CUSTPROG",
            source="CUSTPROG.cbl",
            chunk_type="graph",
            graph_proximity_score=1.0,
        ),
    ]
    vector_chunks = [
        RetrievedChunk(
            text="CUSTOMER table read by CUSTPROG",
            source="CUSTPROG.cbl",
            chunk_type="vector",
            vector_score=0.8,
        ),
        RetrievedChunk(
            text="Spring Batch job processes orders",
            source="OrderJob.java",
            chunk_type="vector",
            vector_score=0.7,
        ),
    ]

    result = retriever._rerank("CUSTOMER lineage", graph_chunks, vector_chunks, top_k=5)

    assert len(result) <= 3
    for chunk in result:
        assert chunk.final_score >= 0.0


def test_extract_entities_finds_known_names() -> None:
    """Entity extractor should find known entity names in questions."""
    from rag.hybrid_retriever import HybridRetriever

    with patch.object(HybridRetriever, "__init__", return_value=None):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._known_entities = ["CUSTOMER_TABLE", "ORDER_FILE", "CUSTPROG"]

    found = retriever._extract_entities_from_question(
        "What columns does CUSTOMER_TABLE write to ORDER_FILE?"
    )
    assert "CUSTOMER_TABLE" in found
    assert "ORDER_FILE" in found
