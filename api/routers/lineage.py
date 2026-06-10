"""Lineage query endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

# ---------------------------------------------------------------------------
# Classification helpers — mirrors the logic in src/agent.py so that nodes
# written by older pipeline runs are corrected at read time without a
# full re-run.
# ---------------------------------------------------------------------------

_LEGACY_TRANSFORM_MAP: dict[str, str] = {
    "program": "COBOLProgram",
    "job":     "JCLUtility",   # will be refined below for Java
}
_LEGACY_ENTITY_MAP: dict[str, str] = {
    "table": "DB2Table",
    "file":  "MainframeDataset",
}


def _classify_entity_name(name: str) -> tuple[str, str]:
    """Return (system, entity_subtype) from a data entity name.

    Mirrors the classification logic in lineage_graph_builder_node so that
    nodes stored by older pipeline runs are corrected at API read time.
    """
    if not name:
        return "z/OS", "MainframeDataset"
    upper = name.upper()
    dot_count = name.count(".")
    schema = name.split(".")[0].upper() if dot_count >= 1 else ""

    if "(" in name:
        return "z/OS", "MainframeDataset"
    if upper.endswith(".XML") or ".XML." in upper:
        return "z/OS", "XMLFile"
    if dot_count >= 2:
        return "z/OS", "MainframeDataset"
    if dot_count == 1:
        table_part = name.split(".", 1)[1].upper()
        if "_" in table_part:
            return "DB2", "DB2Table"
        return "z/OS", "MainframeDataset"

    flat_file_kw = {"FILE", "EXTRACT", "OUTPUT", "INPUT", "LOAD", "REPORT", "TRANS", "REJECT", "VALID"}
    if any(kw in upper for kw in flat_file_kw):
        return "VSAM", "MainframeDataset"
    if any(kw in upper for kw in ("_TABLE", "_LOG", "_MASTER", "_DATA", "_DETAIL", "_SUMMARY")):
        return "DB2", "DB2Table"
    return "VSAM", "MainframeDataset"


def _normalise_node(row: dict[str, Any]) -> dict[str, Any]:
    """Upgrade legacy sub_type/system values on DataEntity nodes."""
    sub_type = row.get("sub_type") or ""
    system   = row.get("system") or ""
    node_type = row.get("type") or ""
    name     = row.get("name") or ""
    language = row.get("language") or ""

    if node_type == "TransformationUnit":
        if sub_type in _LEGACY_TRANSFORM_MAP:
            sub_type = "JavaClass" if language == "java" else _LEGACY_TRANSFORM_MAP[sub_type]
    elif node_type == "DataEntity":
        if sub_type in _LEGACY_ENTITY_MAP or sub_type == "":
            system, sub_type = _classify_entity_name(name)

    return {**row, "sub_type": sub_type, "system": system}


def _get_writer():
    from graph.writer import Neo4jLineageWriter
    from src.config import settings
    return Neo4jLineageWriter(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)


@router.get("/entity/{entity_id}")
async def get_entity_lineage(entity_id: str, depth: int = Query(5, ge=1, le=10)) -> dict[str, Any]:
    """Get upstream and downstream lineage for an entity."""
    try:
        writer = _get_writer()
        upstream = writer.get_upstream_lineage(entity_id, depth)
        downstream = writer.get_downstream_lineage(entity_id, depth)
        writer.close()
        all_nodes = {n["id"]: n for n in upstream["nodes"] + downstream["nodes"]}
        all_edges = upstream["edges"] + downstream["edges"]
        return {"nodes": list(all_nodes.values()), "edges": all_edges}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/column/{table}/{column}")
async def get_column_lineage(table: str, column: str) -> dict[str, Any]:
    """Get column-level lineage for a specific table.column."""
    try:
        writer = _get_writer()
        result = writer.get_column_lineage(table, column)
        writer.close()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/columns/flow")
async def get_column_flow() -> dict[str, Any]:
    """Return the full column-level lineage flow for the Column Data Lineage page.

    Returns entities (with their column lists) and flows (entity-to-entity
    connections with per-step column mapping details and code snippets).
    """
    try:
        from src.neo4j_writer import fetch_all_column_lineage
        return fetch_all_column_lineage()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/end-to-end")
async def get_end_to_end(source: str = Query(...), target: str = Query(...)) -> dict[str, Any]:
    """Get full lineage path from source to target entity."""
    try:
        writer = _get_writer()
        path = writer.get_end_to_end_path(source, target)
        writer.close()
        return {"source": source, "target": target, "path": path}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/impact/{entity_id}")
async def get_impact(entity_id: str, depth: int = Query(5, ge=1, le=10)) -> dict[str, Any]:
    """Get downstream impact analysis for an entity."""
    try:
        writer = _get_writer()
        result = writer.get_downstream_lineage(entity_id, depth)
        writer.close()
        return {"entity_id": entity_id, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/graph")
async def get_full_graph() -> dict[str, Any]:
    """Get full lineage graph for visualisation (capped at 500 nodes).

    Node properties stored by neo4j_writer use ``node_id`` (not ``id``) as
    the unique key, so all Cypher queries must reference ``n.node_id``.
    Edges carry ``edge_id`` and ``relationship``; ``type(r)`` gives the
    relationship *label* which may differ from the stored ``relationship``
    value after normalisation.
    """
    try:
        from neo4j import GraphDatabase
        from src.config import settings
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session() as session:
            node_result = session.run(
                """
                MATCH (n)
                RETURN n.node_id       AS id,
                       n.name          AS name,
                       n.node_type     AS type,
                       n.entity_subtype AS sub_type,
                       n.system        AS system,
                       n.language      AS language,
                       n.schema_name   AS schema
                LIMIT 500
                """
            )
            edge_result = session.run(
                """
                MATCH (a)-[r]->(b)
                RETURN a.node_id    AS source,
                       b.node_id    AS target,
                       r.edge_id    AS id,
                       r.relationship AS relationship,
                       r.confidence AS confidence
                LIMIT 1000
                """
            )
            nodes = [
                _normalise_node({
                    "id":       r["id"],
                    "name":     r["name"] or r["id"],
                    "type":     r["type"] or "DataSource",
                    "sub_type": r["sub_type"] or "",
                    "system":   r["system"] or "",
                    "language": r["language"] or "",
                    "schema":   r["schema"] or "",
                })
                for r in node_result if r["id"]
            ]
            edges = [
                {
                    "id":           r["id"] or f"{r['source']}__{r['target']}",
                    "source":       r["source"],
                    "target":       r["target"],
                    "relationship": r["relationship"] or "TRANSFORMS_VIA",
                    "confidence":   r["confidence"],
                }
                for r in edge_result if r["source"] and r["target"]
            ]
        driver.close()
        return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
async def get_lineage_summary() -> dict[str, Any]:
    """Return aggregate counts used by the Streamlit sidebar stats panel.

    Counts are derived from properties written by neo4j_writer.py:
    node_type ∈ {TransformationUnit, DataEntity} and language/sub_type values
    from the actual extraction pipeline output.
    """
    try:
        from neo4j import GraphDatabase
        from src.config import settings
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                RETURN
                  count(n)                                                      AS total_nodes,
                  count(CASE WHEN n.node_type = 'DataEntity' THEN 1 END)        AS entity_count,
                  count(CASE WHEN n.node_type = 'TransformationUnit' THEN 1 END) AS transform_count,
                  count(CASE WHEN n.language = 'cobol'  THEN 1 END)             AS cobol_count,
                  count(CASE WHEN n.language = 'jcl'    THEN 1 END)             AS job_count,
                  count(CASE WHEN n.language = 'java'   THEN 1 END)             AS java_count,
                  count(CASE WHEN n.node_type = 'DataEntity'
                              AND n.system IN ['DB2','ORACLE','VSAM']
                             THEN 1 END)                                         AS table_count,
                  count(CASE WHEN n.entity_subtype IN ['file','xml','dataset']
                             THEN 1 END)                                         AS output_count
                """
            ).single()
            edge_result = session.run("MATCH ()-[r]->() RETURN count(r) AS edge_count").single()
        driver.close()

        counts = dict(result) if result else {}
        edges = dict(edge_result) if edge_result else {}
        return {
            # Sidebar metrics
            "entity_count":    counts.get("entity_count", 0),
            "job_count":       counts.get("job_count", 0),
            "cobol_count":     counts.get("cobol_count", 0),
            "output_count":    counts.get("output_count", 0),
            # Extended breakdown
            "total_nodes":     counts.get("total_nodes", 0),
            "transform_count": counts.get("transform_count", 0),
            "java_count":      counts.get("java_count", 0),
            "table_count":     counts.get("table_count", 0),
            "edge_count":      edges.get("edge_count", 0),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/search")
async def search_nodes(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    """Full-text search over lineage node names and IDs."""
    try:
        from neo4j import GraphDatabase
        from src.config import settings
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE toLower(coalesce(n.name, ''))        CONTAINS toLower($q)
                   OR toLower(coalesce(n.node_id, ''))     CONTAINS toLower($q)
                   OR toLower(coalesce(n.language, ''))    CONTAINS toLower($q)
                   OR toLower(coalesce(n.system, ''))      CONTAINS toLower($q)
                   OR toLower(coalesce(n.entity_subtype,'')) CONTAINS toLower($q)
                RETURN n.node_id       AS id,
                       n.name          AS name,
                       n.node_type     AS type,
                       n.entity_subtype AS sub_type,
                       n.system        AS system,
                       n.language      AS language
                LIMIT 50
                """,
                q=q,
            )
            nodes = [
                {
                    "id":       r["id"],
                    "name":     r["name"] or r["id"],
                    "type":     r["type"] or "DataSource",
                    "sub_type": r["sub_type"] or "MainframeDataset",
                    "system":   r["system"] or "",
                    "language": r["language"] or "",
                    "schema":   "",
                }
                for r in result if r["id"]
            ]
        driver.close()
        return {"nodes": nodes, "edges": []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
