"""sqlglot lineage tool — deterministic SQL column lineage."""
from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool


@tool
def sqlglot_lineage_tool(
    sql_query: Annotated[str, "SQL SELECT or INSERT statement to trace column lineage"],
    column_name: Annotated[str, "Target column name to trace upstream"],
    dialect: Annotated[str, "SQL dialect: db2 | oracle | postgres | mysql | ansi"] = "ansi",
) -> str:
    """Run sqlglot column-level lineage tracing on a SQL statement.

    Returns JSON describing all upstream sources for the specified target column.
    This is deterministic — no LLM involved. Use to verify SQL column assertions.
    """
    try:
        import sqlglot.lineage

        node = sqlglot.lineage.lineage(column_name, sql_query, dialect=dialect)
        result: dict[str, Any] = {
            "column": column_name,
            "sql": sql_query[:200],
            "upstream": [],
        }
        if node:

            def _walk(current_node: Any, depth: int = 0) -> list[dict[str, Any]]:
                items = [{"name": str(current_node.name), "source": str(current_node.source)[:100], "depth": depth}]
                for child in getattr(current_node, "downstream", []):
                    items.extend(_walk(child, depth + 1))
                return items

            result["upstream"] = _walk(node)
        return json.dumps(result, indent=2)
    except ImportError:
        return json.dumps({"error": "sqlglot not installed. Run: uv add sqlglot"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
