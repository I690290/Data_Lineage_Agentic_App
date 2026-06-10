"""Neo4j query tool — Cypher queries against the lineage graph."""
from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool


@tool
def neo4j_query_tool(
    cypher_query: Annotated[str, "Cypher query to execute against the Neo4j lineage graph"],
) -> str:
    """Execute a read-only Cypher query on the Neo4j lineage graph.

    Returns JSON list of result rows. Use for upstream/downstream lineage tracing.
    Example: MATCH (n)-[r:READS_FROM]->(m) RETURN n.name, m.name LIMIT 10
    """
    from neo4j import GraphDatabase

    from src.config import settings

    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        with driver.session() as session:
            records = session.run(cypher_query)
            data: list[dict[str, Any]] = [dict(record) for record in records]
        driver.close()
        return json.dumps(data, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
