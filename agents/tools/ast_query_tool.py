"""AST query tool — query parsed ASTs for specific node types."""
from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool


@tool
def ast_query_tool(
    file_path: Annotated[str, "Path to the source file to query"],
    query_type: Annotated[str, "Type of AST node to find: 'io_operations', 'data_movements', 'calls', 'all'"],
    filter_name: Annotated[str, "Optional: filter by name (e.g. variable or table name)"] = "",
) -> str:
    """Query the parsed AST of a source file for specific structural nodes.

    Returns JSON list of matching operations with file, line, and type metadata.
    Use for programmatic verification of lineage assertions.
    """
    from parsers.orchestrator import ParserOrchestrator

    orchestrator = ParserOrchestrator()
    chunks = orchestrator.parse_file(file_path)
    results: list[dict[str, Any]] = []

    for chunk in chunks:
        if query_type in ("io_operations", "all"):
            for operation in chunk.io_operations:
                if not filter_name or filter_name.upper() in str(operation.get("target", "")).upper():
                    results.append({**operation, "chunk_ast_path": chunk.ast_path, "file_path": file_path})
        if query_type in ("data_movements", "all"):
            for movement in chunk.data_movements:
                if not filter_name or (
                    filter_name.upper() in str(movement.get("source", "")).upper()
                    or filter_name.upper() in str(movement.get("target", "")).upper()
                ):
                    results.append({**movement, "chunk_ast_path": chunk.ast_path, "file_path": file_path})

    return json.dumps(results, indent=2)
