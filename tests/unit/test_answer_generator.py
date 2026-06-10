"""Unit tests for AnswerGenerator."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from models.lineage_models import RagAnswer, RetrievedChunk


def _make_chunks() -> list[RetrievedChunk]:
    """Build sample retrieved chunks."""
    return [
        RetrievedChunk(
            text="CUSTOMER_TABLE is read by CUSTPROG paragraph PROCESS-CUST",
            source="CUSTPROG.cbl",
            chunk_type="graph",
            vector_score=0.9,
        ),
        RetrievedChunk(
            text="ORDER_FILE is written by CUSTPROG in paragraph WRITE-ORDER",
            source="CUSTPROG.cbl",
            chunk_type="vector",
            vector_score=0.8,
        ),
    ]


def test_sync_generate_returns_rag_answer() -> None:
    """AnswerGenerator.generate(stream=False) should return RagAnswer."""
    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="CUSTPROG reads CUSTOMER_TABLE [1] and writes ORDER_FILE [2].\nSOURCES:\n[1] CUSTPROG.cbl | graph | ...\n[2] CUSTPROG.cbl | vector | ..."
    )

    with patch("rag.answer_generator.ChatBedrockConverse", return_value=mock_llm), patch(
        "rag.answer_generator.boto3.client", return_value=MagicMock()
    ):
        from rag.answer_generator import AnswerGenerator

        generator = AnswerGenerator()
        generator._llm = mock_llm
        result = generator.generate("What does CUSTPROG do?", _make_chunks(), stream=False)

    assert isinstance(result, RagAnswer)
    assert "CUSTPROG" in result.answer_text
    assert len(result.citations) >= 1


def test_parse_citations_extracts_keys() -> None:
    """_parse_citations should extract all unique citation keys."""
    from rag.answer_generator import _parse_citations

    chunks = _make_chunks()
    answer = "CUSTPROG reads CUSTOMER_TABLE [1] and writes to ORDER_FILE [2]. See [1] for details."
    citations = _parse_citations(answer, chunks)

    assert len(citations) == 2
    keys = [citation.key for citation in citations]
    assert "[1]" in keys
    assert "[2]" in keys
