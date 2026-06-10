"""ReAct extraction agents — one per language, sharing a common loop."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.reflexion import ReflexionRetry
from config.models import get_model_config
from config.settings import settings


_reflexion = ReflexionRetry(max_retries=settings.reflexion_max_retries)

_SYSTEM_PROMPTS: dict[str, str] = {}


def _load_prompt(language: str) -> str:
    """Load and cache the system prompt for a language.

    Args:
        language: One of ``"cobol"``, ``"java"``, ``"sql"``.

    Returns:
        System prompt text.
    """
    if language not in _SYSTEM_PROMPTS:
        prompt_dir = Path(__file__).parent / "prompts"
        prompt_file = prompt_dir / f"{language.lower()}_system.txt"
        if prompt_file.exists():
            _SYSTEM_PROMPTS[language] = prompt_file.read_text(encoding="utf-8")
        else:
            _SYSTEM_PROMPTS[language] = (
                f"You are a {language} data lineage extraction agent. "
                "Extract all data lineage assertions as a JSON array."
            )
    return _SYSTEM_PROMPTS[language]


def _make_llm(model_id: str | None = None) -> ChatBedrockConverse:
    """Instantiate the Bedrock LLM for extraction.

    Args:
        model_id: Optional override; defaults to ``settings.bedrock_text_model_id``.

    Returns:
        Configured ``ChatBedrockConverse`` instance.
    """
    mid = model_id or settings.bedrock_text_model_id
    model_cfg = get_model_config(mid)
    return ChatBedrockConverse(
        model=mid,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token or None,
        temperature=model_cfg.temperature,
        max_tokens=model_cfg.max_tokens,
    )


def _parse_assertions(raw: str) -> list[dict[str, Any]]:
    """Parse JSON assertions from LLM response text.

    Args:
        raw: Raw string response from the LLM.

    Returns:
        List of assertion dicts (may be empty if parsing fails).
    """
    # Try direct JSON array
    json_match = re.search(r"\[[\s\S]*\]", raw)
    if json_match:
        try:
            items = json.loads(json_match.group(0))
            if isinstance(items, list):
                # Ensure each assertion has an id
                for item in items:
                    if "id" not in item:
                        item["id"] = str(uuid.uuid4())
                return items
        except json.JSONDecodeError:
            pass
    return []


def _build_extraction_prompt(
    chunk: Any,  # ChunkMetadata
    language: str,
    episodic_memory: list[str],
) -> str:
    """Build the human-turn extraction prompt for a single chunk.

    Args:
        chunk: ChunkMetadata object being analysed.
        language: Source language tag.
        episodic_memory: Past failure context for Reflexion retries.

    Returns:
        Formatted prompt string.
    """
    retry_context = _reflexion.build_retry_context(episodic_memory)
    parts = []
    if retry_context:
        parts.append(retry_context)
    parts.extend([
        f"FILE: {chunk.file_path}",
        f"LANGUAGE: {language}",
        f"AST PATH: {chunk.ast_path}",
        f"STRUCTURAL TYPE: {chunk.structural_type}",
        f"LINES: {chunk.start_line}-{chunk.end_line}",
    ])
    if chunk.io_operations:
        parts.append(f"I/O OPERATIONS: {json.dumps(chunk.io_operations[:10])}")
    if chunk.data_movements:
        parts.append(f"DATA MOVEMENTS: {json.dumps(chunk.data_movements[:10])}")
    parts.extend([
        "",
        "SOURCE CODE:",
        "```",
        chunk.content[:6000] + ("\n... [truncated]" if len(chunk.content) > 6000 else ""),
        "```",
        "",
        "Extract ALL data lineage assertions from this code chunk. Return ONLY the JSON array.",
    ])
    return "\n".join(parts)


def _run_react_loop(
    language: str,
    chunks: list[Any],  # list[ChunkMetadata]
    episodic_memory: list[str],
    llm: ChatBedrockConverse,
) -> list[dict[str, Any]]:
    """Execute the ReAct extraction loop over all chunks.

    For each chunk: THINK (build prompt) → ACT (invoke LLM) → OBSERVE (parse)
    → ASSERT (collect results).

    Args:
        language: Source language tag.
        chunks: Parsed ChunkMetadata objects.
        episodic_memory: Accumulated failure context from previous retries.
        llm: Bedrock LLM instance.

    Returns:
        Flat list of all extracted assertion dicts.
    """
    all_assertions: list[dict[str, Any]] = []
    system_prompt = _load_prompt(language)

    for chunk in chunks:
        # Skip empty or trivially small chunks
        if len(chunk.content.strip()) < 20:
            continue

        # THINK + ACT: build prompt and invoke
        human_prompt = _build_extraction_prompt(chunk, language, episodic_memory)
        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw = response.content if isinstance(response.content, str) else str(response.content)
        except Exception as exc:
            print(f"[react_agent] LLM invocation failed for {chunk.file_path}:{chunk.ast_path}: {exc}")
            continue

        # OBSERVE + ASSERT
        assertions = _parse_assertions(raw)
        if not assertions:
            print(f"[react_agent] No assertions parsed from {chunk.ast_path} (len={len(raw)})")
        for assertion in assertions:
            assertion["_source_chunk"] = chunk.ast_path
            assertion["_file_path"] = chunk.file_path
        all_assertions.extend(assertions)

    return all_assertions


def cobol_extraction_agent(state: dict[str, Any]) -> dict[str, Any]:
    """ReAct agent for COBOL data lineage extraction.

    Args:
        state: Current LangGraph LineageState dict.

    Returns:
        Updated state with ``extracted_assertions`` populated.
    """
    print("[cobol_agent] Starting COBOL extraction")
    chunks = state.get("chunks", [])
    episodic_memory = state.get("episodic_memory", [])
    llm = _make_llm()
    assertions = _run_react_loop("COBOL", chunks, episodic_memory, llm)
    print(f"[cobol_agent] Extracted {len(assertions)} assertions")
    return {**state, "extracted_assertions": assertions, "language": "cobol"}


def java_extraction_agent(state: dict[str, Any]) -> dict[str, Any]:
    """ReAct agent for Java data lineage extraction.

    Args:
        state: Current LangGraph LineageState dict.

    Returns:
        Updated state with ``extracted_assertions`` populated.
    """
    print("[java_agent] Starting Java extraction")
    chunks = state.get("chunks", [])
    episodic_memory = state.get("episodic_memory", [])
    llm = _make_llm()
    assertions = _run_react_loop("Java", chunks, episodic_memory, llm)
    print(f"[java_agent] Extracted {len(assertions)} assertions")
    return {**state, "extracted_assertions": assertions, "language": "java"}


def sql_extraction_agent(state: dict[str, Any]) -> dict[str, Any]:
    """ReAct agent for SQL data lineage extraction.

    Args:
        state: Current LangGraph LineageState dict.

    Returns:
        Updated state with ``extracted_assertions`` populated.
    """
    print("[sql_agent] Starting SQL extraction")
    chunks = state.get("chunks", [])
    episodic_memory = state.get("episodic_memory", [])
    llm = _make_llm()
    assertions = _run_react_loop("SQL", chunks, episodic_memory, llm)
    print(f"[sql_agent] Extracted {len(assertions)} assertions")
    return {**state, "extracted_assertions": assertions, "language": "sql"}
