"""Unit tests for SSE streaming utility."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from streamlit_app.utils.streaming import CitationsPayload, stream_rag_response


def test_citations_payload_is_sentinel() -> None:
    """CitationsPayload should be distinguishable from string tokens."""
    payload = CitationsPayload(citations=[{"key": "[1]", "source_file": "f.cbl"}])
    assert isinstance(payload, CitationsPayload)
    assert not isinstance(payload, str)
    assert payload.citations[0]["key"] == "[1]"


def test_stream_rag_response_handles_connection_error() -> None:
    """stream_rag_response should yield an error string on connection failure."""
    import httpx

    with patch("streamlit_app.utils.streaming.httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.stream.side_effect = httpx.ConnectError("refused")

        tokens = list(
            stream_rag_response("test question", api_base_url="http://localhost:9999")
        )

    assert len(tokens) >= 1
    assert any(
        "Connection error" in str(token) or "error" in str(token).lower()
        for token in tokens
    )
