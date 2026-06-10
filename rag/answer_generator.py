"""
RAG answer generator using Amazon Nova Pro.
Supports both streaming and non-streaming modes with citation output.
"""
from __future__ import annotations

import json
import re
from typing import Generator

import boto3
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from config.models import BedrockModels
from models.lineage_models import Citation, RagAnswer, RetrievedChunk
from src.config import settings


_SYSTEM_PROMPT = """You are a data lineage expert assistant. Answer questions about data lineage, transformations, and source-to-target mappings.

Instructions:
- Respond in 3-5 sentences maximum
- Inline EVERY factual claim with its citation key in square brackets, e.g. "The CUSTOMER_TABLE is read by CUSTPROG [1]"
- Do NOT hallucinate beyond the provided context — if you don't know, say so
- End your response with a SOURCES: block listing each cited chunk:
  SOURCES:
  [1] file_path | chunk_type | brief description
  [2] ...
- If the context is insufficient, say "I don't have enough context to answer this question."
"""


def _build_rag_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Build a labelled RAG prompt from retrieved chunks."""
    context_lines = []
    for index, chunk in enumerate(chunks, 1):
        context_lines.append(
            f"[{index}] Source: {chunk.source} (type: {chunk.chunk_type})\n{chunk.text[:800]}"
        )
    context = "\n\n---\n\n".join(context_lines)
    return f"""Context (use citations [1]-[{len(chunks)}]):

{context}

---

Question: {question}

Answer (inline citations required):"""


def _parse_citations(answer_text: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Parse unique citation keys from the answer text."""
    cited_keys = re.findall(r"\[(\d+)\]", answer_text)
    citations: list[Citation] = []
    seen_keys: set[str] = set()
    for key_str in cited_keys:
        if key_str in seen_keys:
            continue
        seen_keys.add(key_str)
        idx = int(key_str) - 1
        if 0 <= idx < len(chunks):
            chunk = chunks[idx]
            citations.append(
                Citation(
                    key=f"[{key_str}]",
                    source_file=chunk.source,
                    chunk_type=chunk.chunk_type,
                    snippet=chunk.text[:300],
                )
            )
    return citations


class AnswerGenerator:
    """Generate grounded RAG answers using Amazon Nova Pro."""

    def __init__(self) -> None:
        """Initialise Bedrock clients for sync and streaming generation."""
        self._llm = ChatBedrockConverse(
            model=BedrockModels.NOVA_PRO,
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token or None,
            temperature=0.1,
            max_tokens=1024,
        )
        self._bedrock_runtime = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token or None,
        )

    def generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        stream: bool = False,
    ) -> RagAnswer | Generator[str, None, None]:
        """Generate a grounded answer.

        Args:
            question: The user question.
            chunks: Retrieved context chunks.
            stream: Whether to stream token output.

        Returns:
            A RagAnswer or a token generator.
        """
        if stream:
            return self._stream_generate(question, chunks)
        return self._sync_generate(question, chunks)

    def _sync_generate(self, question: str, chunks: list[RetrievedChunk]) -> RagAnswer:
        """Generate a non-streaming answer."""
        prompt = _build_rag_prompt(question, chunks)
        response = self._llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        raw_content = response.content
        answer_text = raw_content if isinstance(raw_content, str) else str(raw_content)
        citations = _parse_citations(answer_text, chunks)
        return RagAnswer(answer_text=answer_text, citations=citations)

    def _stream_generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> Generator[str, None, None]:
        """Generate a streaming answer and emit a final citations sentinel."""
        prompt = _build_rag_prompt(question, chunks)
        body = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": [{"text": f"{_SYSTEM_PROMPT}\n\n{prompt}"}]}
                ],
                "inferenceConfig": {"maxTokens": 1024, "temperature": 0.1},
            }
        )
        try:
            response = self._bedrock_runtime.invoke_model_with_response_stream(
                modelId=BedrockModels.NOVA_PRO,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            full_text = ""
            for event in response["body"]:
                chunk_data = event.get("chunk", {})
                if not chunk_data:
                    continue
                chunk_json = json.loads(chunk_data.get("bytes", b"{}"))
                delta = (
                    chunk_json.get("contentBlockDelta", {})
                    .get("delta", {})
                    .get("text", "")
                )
                if delta:
                    full_text += delta
                    yield delta

            citations = _parse_citations(full_text, chunks)
            citations_data = [
                {
                    "key": citation.key,
                    "source_file": citation.source_file,
                    "chunk_type": citation.chunk_type,
                    "snippet": citation.snippet,
                }
                for citation in citations
            ]
            yield f"\n__CITATIONS__{json.dumps(citations_data)}__END_CITATIONS__"
        except Exception as exc:
            yield f"Error generating answer: {exc}"
