"""Neo4j lineage graph writer with full CRUD and lineage query helpers."""
from __future__ import annotations

import json
from typing import Any

from graph.schema import CONSTRAINT_QUERIES


class Neo4jLineageWriter:
    """Write and query data lineage in a Neo4j graph.

    Handles upsert semantics so nodes and edges are idempotent across
    multiple pipeline runs. Initialises schema constraints on first use.

    Args:
        uri: Neo4j Bolt URI.
        user: Neo4j username.
        password: Neo4j password.
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_schema()

    def _init_schema(self) -> None:
        """Apply schema constraints and indexes on first connection."""
        try:
            with self._driver.session() as session:
                for query in CONSTRAINT_QUERIES:
                    session.run(query)
        except Exception as exc:
            print(f"[neo4j_writer] Schema init warning (non-fatal): {exc}")

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        self._driver.close()

    def create_node(self, node_type: str, properties: dict[str, Any]) -> str:
        """Upsert a node and return its ``id`` property.

        Args:
            node_type: Neo4j label (e.g. ``"Table"``).
            properties: Property dict; must include ``name`` or ``id``.

        Returns:
            The ``id`` value of the upserted node.
        """
        node_id = properties.get("id") or properties.get("name", "unknown")
        properties["id"] = node_id
        query = (
            f"MERGE (n:{node_type} {{id: $id}}) "
            "SET n += $props "
            "RETURN n.id AS node_id"
        )
        with self._driver.session() as session:
            result = session.run(query, id=node_id, props=properties)
            record = result.single()
            return record["node_id"] if record else node_id

    def create_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Create or update a directed edge between two nodes.

        Args:
            from_id: ``id`` property of the source node.
            to_id: ``id`` property of the target node.
            edge_type: Relationship type (e.g. ``"READS_FROM"``).
            properties: Optional edge properties.
        """
        props = properties or {}
        query = (
            "MATCH (a {id: $from_id}), (b {id: $to_id}) "
            f"MERGE (a)-[r:{edge_type}]->(b) "
            "SET r += $props"
        )
        with self._driver.session() as session:
            session.run(query, from_id=from_id, to_id=to_id, props=props)

    def upsert_lineage(self, openlineage_events: list[dict[str, Any]]) -> None:
        """Convert OpenLineage events to Neo4j nodes and edges.

        Args:
            openlineage_events: List of OpenLineage RunEvent dicts.
        """
        for event in openlineage_events:
            job = event.get("job", {})
            job_name = job.get("name", "unknown")
            job_id = f"job_{job_name}"

            # Create Job/Program node
            self.create_node("Program", {
                "id": job_id,
                "name": job_name,
                "namespace": job.get("namespace", ""),
                "language": event.get("run", {}).get("facets", {}).get("extractionConfig", {}).get("language", ""),
                "confidence": event.get("run", {}).get("facets", {}).get("extractionConfig", {}).get("confidence", 0.0),
            })

            # Create input dataset nodes + READS_FROM edges
            for inp in event.get("inputs", []):
                inp_name = inp.get("name", "unknown")
                inp_id = f"dataset_{inp_name}"
                self.create_node("File", {
                    "id": inp_id,
                    "name": inp_name,
                    "namespace": inp.get("namespace", ""),
                    "type": inp.get("type", "unknown"),
                })
                self.create_edge(job_id, inp_id, "READS_FROM", {
                    "confidence": inp.get("confidence", 0.5),
                    "source_location": "",
                    "transformation_logic": "",
                })

            # Create output dataset nodes + WRITES_TO edges
            for out in event.get("outputs", []):
                out_name = out.get("name", "unknown")
                out_id = f"dataset_{out_name}"
                self.create_node("Table", {
                    "id": out_id,
                    "name": out_name,
                    "namespace": out.get("namespace", ""),
                    "type": out.get("type", "unknown"),
                })
                self.create_edge(job_id, out_id, "WRITES_TO", {
                    "confidence": out.get("confidence", 0.5),
                    "source_location": "",
                    "transformation_logic": "",
                })

                # Column lineage edges
                col_lineage = out.get("facets", {}).get("columnLineage", {}).get("fields", {})
                for target_col, lineage_info in col_lineage.items():
                    tgt_col_id = f"col_{out_name}_{target_col}"
                    self.create_node("Column", {
                        "id": tgt_col_id,
                        "name": target_col,
                        "table": out_name,
                        "nullable": True,
                        "data_type": "unknown",
                    })
                    self.create_edge(out_id, tgt_col_id, "DEFINED_IN", {"file_path": "", "start_line": 0})

                    for src_field in lineage_info.get("inputFields", []):
                        src_col_name = src_field.get("field", "")
                        src_tbl = src_field.get("dataset", "")
                        src_col_id = f"col_{src_tbl}_{src_col_name}"
                        self.create_node("Column", {
                            "id": src_col_id,
                            "name": src_col_name,
                            "table": src_tbl,
                            "nullable": True,
                            "data_type": "unknown",
                        })
                        self.create_edge(src_col_id, tgt_col_id, "MAPS_TO", {
                            "mapping_type": lineage_info.get("transformationType", "UNKNOWN"),
                            "expression": lineage_info.get("transformationDescription", ""),
                            "confidence": 0.9,
                        })

    def get_upstream_lineage(self, node_id: str, depth: int = 5) -> dict[str, Any]:
        """Get all upstream nodes up to ``depth`` hops.

        Args:
            node_id: The ``id`` of the target node.
            depth: Maximum number of hops to traverse.

        Returns:
            Dict with ``nodes`` and ``edges`` lists.
        """
        query = (
            f"MATCH path = (upstream)-[*1..{depth}]->(n {{id: $node_id}}) "
            "RETURN nodes(path) AS nodes, relationships(path) AS rels"
        )
        return self._run_path_query(query, node_id=node_id)

    def get_downstream_lineage(self, node_id: str, depth: int = 5) -> dict[str, Any]:
        """Get all downstream nodes up to ``depth`` hops.

        Args:
            node_id: The ``id`` of the source node.
            depth: Maximum number of hops to traverse.

        Returns:
            Dict with ``nodes`` and ``edges`` lists.
        """
        query = (
            f"MATCH path = (n {{id: $node_id}})-[*1..{depth}]->(downstream) "
            "RETURN nodes(path) AS nodes, relationships(path) AS rels"
        )
        return self._run_path_query(query, node_id=node_id)

    def get_column_lineage(self, table: str, column: str) -> dict[str, Any]:
        """Get column-level lineage for a specific table.column.

        Args:
            table: Table name.
            column: Column name.

        Returns:
            Dict with ``upstream_columns`` list.
        """
        query = (
            "MATCH (tgt:Column {table: $table, name: $column})"
            "<-[r:MAPS_TO*1..5]-(src:Column) "
            "RETURN src.table AS source_table, src.name AS source_column, "
            "r[-1].expression AS transformation, r[-1].confidence AS confidence"
        )
        with self._driver.session() as session:
            records = session.run(query, table=table, column=column)
            return {"upstream_columns": [dict(r) for r in records]}

    def get_end_to_end_path(self, source: str, target: str) -> list[dict[str, Any]]:
        """Find the shortest lineage path between two entities.

        Args:
            source: Source entity name or id.
            target: Target entity name or id.

        Returns:
            List of node/edge dicts along the path.
        """
        query = (
            "MATCH path = shortestPath((a {name: $source})-[*1..10]->(b {name: $target})) "
            "RETURN [node IN nodes(path) | {id: node.id, name: node.name, labels: labels(node)}] AS path_nodes, "
            "[rel IN relationships(path) | {type: type(rel), confidence: rel.confidence}] AS path_rels"
        )
        with self._driver.session() as session:
            records = list(session.run(query, source=source, target=target))
            if records:
                r = records[0]
                return [
                    {"node": n, "edge": e}
                    for n, e in zip(r["path_nodes"], r["path_rels"] + [{}])
                ]
        return []

    def _run_path_query(self, query: str, **params: Any) -> dict[str, Any]:
        """Execute a path query and return serialisable node/edge dicts."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        try:
            with self._driver.session() as session:
                records = session.run(query, **params)
                for record in records:
                    for node in record.get("nodes", []):
                        nid = node.get("id", str(node.id))
                        if nid not in seen_nodes:
                            seen_nodes.add(nid)
                            nodes.append({"id": nid, "properties": dict(node), "labels": list(node.labels)})
                    for rel in record.get("rels", []):
                        edges.append({
                            "type": rel.type,
                            "from": rel.start_node.get("id", ""),
                            "to": rel.end_node.get("id", ""),
                            "properties": dict(rel),
                        })
        except Exception as exc:
            print(f"[neo4j_writer] Query error: {exc}")
        return {"nodes": nodes, "edges": edges}
