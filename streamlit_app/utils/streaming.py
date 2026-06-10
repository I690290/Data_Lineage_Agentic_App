"""SSE stream consumer for token-by-token streaming from FastAPI."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generator

import httpx

from streamlit_app.config import FASTAPI_BASE_URL


@dataclass
class CitationsPayload:
    """Sentinel object wrapping final citations from the SSE stream."""

    citations: list[dict]


def stream_rag_response(
    question: str,
    api_base_url: str = FASTAPI_BASE_URL,
    max_chunks: int = 8,
) -> Generator[str | CitationsPayload, None, None]:
    """Stream tokens from the FastAPI SSE endpoint.

    Args:
        question: User question.
        api_base_url: Base URL of the FastAPI app.
        max_chunks: Maximum retrieved chunks.

    Yields:
        Token strings followed by a citations sentinel.
    """
    url = f"{api_base_url.rstrip('/')}/rag/ask"
    payload = {"question": question, "stream": True, "max_chunks": max_chunks}

    try:
        with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
            with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    yield f"Error: API returned {response.status_code}"
                    return

                current_event = "message"
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        continue
                    if not line.startswith("data:"):
                        continue

                    # SSE format is "data: <content>" — skip exactly one separator
                    # space after "data:" but preserve any spaces inside the token
                    # (e.g. Bedrock yields " is", " the" with leading spaces).
                    # Using .strip() would silently delete those spaces, merging words.
                    raw = line[6:] if line.startswith("data: ") else line[5:]
                    if current_event == "citations":
                        try:
                            yield CitationsPayload(citations=json.loads(raw))
                        except Exception:
                            yield CitationsPayload(citations=[])
                    else:
                        yield raw
    except httpx.ConnectError:
        yield f"Connection error: Could not reach API at {api_base_url}"
    except Exception as exc:
        yield f"Streaming error: {exc}"
