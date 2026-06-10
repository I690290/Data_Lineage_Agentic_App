"""
LangGraph node: column_lineage_extraction_node

Extracts field-level lineage from COBOL, JCL, Oracle SQL, and Java source files
using Amazon Nova Lite.  Runs AFTER code_analysis_node and BEFORE lineage_graph_builder_node.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from config.models import BedrockModels
from models.lineage_models import ColumnLineageRecord
from src.config import settings
from src.models import AgentState, AnalysisResult


_COLUMN_LINEAGE_SYSTEM_PROMPT = """You are a data lineage expert specialising in field-level lineage extraction.
Analyse the provided source code and extract ALL field/column-level mappings.

You MUST respond with ONLY a valid JSON array (no preamble, no markdown):
[
  {
    "source_column": "<field or column name read>",
    "transformation_name": "<COBOL paragraph, SQL statement name, or JCL step name>",
    "transformation_type": "<MOVE|COMPUTE|STRING|INSERT_SELECT|LOAD_POSITION|CREATE_VIEW|EXTERNAL_FIELD|SORT_FIELD|PERFORM>",
    "transformation_code_snippet": "<exact code line(s) responsible, max 3 lines>",
    "target_column": "<field or column name written>",
    "confidence_score": <float 0.0-1.0>
  }
]

Rules:
- For COBOL: extract from MOVE, COMPUTE, STRING, UNSTRING, EVALUATE, PERFORM statements
- For Oracle/SQL LOAD DATA files: each POSITION(x:y) entry maps source file field to table column
  — use "FIELD_POS_x_y" as source_column, use the target column name in the table as target_column
- For Oracle EXTERNAL TABLE DDL: each XML tag ENCLOSED BY '<tag>' maps to a table column
  — use the XML tag name as source_column, the column name as target_column
- For INSERT INTO ... SELECT: each SELECT expression maps to the corresponding INSERT column
  — use source expression (e.g. TRIM(e.MAIN_ACCOUNT_NUMBER)) as source_column, INSERT column name as target_column
- For CREATE VIEW ... AS SELECT: each selected column maps from source table.column to view column
  — use TABLE.COLUMN as source_column (or expression), VIEW_COLUMN_NAME as target_column
- transformation_name must be the SQL script stem (e.g. MI4014_EXT_TABLE) for SQL files
- source_column and target_column must be the actual field/column names
- If no field mappings found, return empty array []
"""


def _make_nova_lite_llm() -> ChatBedrockConverse:
    """Create a Nova Lite LLM instance for column lineage extraction."""
    return ChatBedrockConverse(
        model=BedrockModels.NOVA_LITE,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token or None,
        temperature=0.0,
        max_tokens=4096,
    )


def _extract_column_lineage_for_file(
    file_path: str,
    language: str,
    analysis_result: AnalysisResult,
    llm: ChatBedrockConverse,
) -> list[ColumnLineageRecord]:
    """Extract column-level lineage for a single file using Nova Lite.

    Supported languages: cobol, jcl, sql (Oracle DDL/DML), java.

    Args:
        file_path: Path to source file.
        language: Language identifier.
        analysis_result: Existing analysis result with entity-level lineage.
        llm: Nova Lite LLM instance.

    Returns:
        List of extracted column lineage records.
    """
    if language not in ("cobol", "java", "jcl", "sql"):
        return []
    if language != "sql" and not analysis_result.reads_from and not analysis_result.writes_to:
        return []

    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    program_stem = Path(file_path).stem.upper()
    truncated = content[:7000] + ("\n... [truncated]" if len(content) > 7000 else "")
    source_entities = ", ".join(analysis_result.reads_from[:5]) or "unknown"
    target_entities = ", ".join(analysis_result.writes_to[:5]) or "unknown"

    language_hint = ""
    if language == "jcl":
        language_hint = (
            "\nFor JCL: Focus on SORT FIELDS= cards. "
            "SORT FIELDS=(start,length,type,direction) — use FIELD_POS_start_length as column names. "
            "OUTREC FIELDS= defines output positions and transformations."
        )
    elif language == "sql":
        language_hint = (
            "\nFor Oracle SQL: "
            "In LOAD DATA...POSITION(x:y) blocks: source_column = 'FIELD_POS_x_y', "
            "target_column = the column name in the INTO TABLE. "
            "In EXTERNAL TABLE...FIELDS ENCLOSED BY '<tag>': source_column = XML tag name, "
            "target_column = column name. "
            "In INSERT INTO ... SELECT: source_column = SELECT expression, "
            "target_column = INSERT column. "
            "In CREATE VIEW ... AS SELECT: source_column = table.column (or expression), "
            "target_column = view alias or column. "
            f"Use '{program_stem}' as transformation_name for all mappings in this file."
        )

    user_prompt = f"""File: {file_path}
Language: {language}
Program name: {program_stem}
Source entities (reads from): {source_entities}
Target entities (writes to): {target_entities}
{language_hint}

Source code:
```
{truncated}
```

Extract all field/column-level lineage mappings. Return ONLY the JSON array."""

    try:
        response = llm.invoke([
            SystemMessage(content=_COLUMN_LINEAGE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw_content = response.content
        raw = raw_content if isinstance(raw_content, str) else str(raw_content)
        array_match = re.search(r"\[[\s\S]*\]", raw)
        if not array_match:
            return []

        records_data: list[dict[str, Any]] = json.loads(array_match.group(0))
        if not isinstance(records_data, list):
            return []

        results: list[ColumnLineageRecord] = []
        for item in records_data:
            if not isinstance(item, dict):
                continue
            source_col = str(item.get("source_column", "")).strip()
            target_col = str(item.get("target_column", "")).strip()
            if not source_col or not target_col:
                continue

            source_file = analysis_result.reads_from[0] if analysis_result.reads_from else file_path
            target_file = analysis_result.writes_to[0] if analysis_result.writes_to else file_path
            confidence = float(item.get("confidence_score", 0.5))
            results.append(
                ColumnLineageRecord(
                    source_file=source_file,
                    source_column=source_col,
                    transformation_name=str(item.get("transformation_name", program_stem)),
                    transformation_type=str(item.get("transformation_type", "UNKNOWN")),
                    transformation_code_snippet=str(item.get("transformation_code_snippet", "")),
                    target_file=target_file,
                    target_column=target_col,
                    program_file_path=file_path,
                    program_name=program_stem,
                    confidence_score=confidence,
                )
            )
        return results
    except Exception as exc:
        print(f"[column_lineage] Error processing {file_path}: {exc}")
        return []


def column_lineage_extraction_node(state: AgentState) -> AgentState:
    """Extract column-level lineage for COBOL, JCL, Oracle SQL, and Java source files.

    Args:
        state: Current agent state with populated analysis_results.

    Returns:
        Updated state containing column_lineage_records.
    """
    _ELIGIBLE = {"cobol", "jcl", "sql", "java"}
    analysis_results = state.get("analysis_results", {})
    eligible_results = [r for r in analysis_results.values() if r.language in _ELIGIBLE]
    if not analysis_results:
        print("[column_lineage] No analysis results found — skipping")
        return {**state, "column_lineage_records": []}
    if not eligible_results:
        print("[column_lineage] No eligible files (COBOL/JCL/SQL) found — skipping")
        return {**state, "column_lineage_records": []}

    llm = _make_nova_lite_llm()
    all_records: list[ColumnLineageRecord] = []
    for file_path, result in analysis_results.items():
        if result.language not in _ELIGIBLE:
            continue
        print(f"[column_lineage] Extracting field mappings from {file_path} ({result.language})")
        records = _extract_column_lineage_for_file(file_path, result.language, result, llm)
        all_records.extend(records)
        print(f"  → {len(records)} column lineage records")

    print(f"[column_lineage] Total: {len(all_records)} column lineage records")
    return {**state, "column_lineage_records": all_records}
