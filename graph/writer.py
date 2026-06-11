"""Neo4j lineage graph writer with full CRUD and lineage query helpers."""
from __future__ import annotations

import json
import re
from typing import Any

from graph.schema import CONSTRAINT_QUERIES, entity_type_to_neo4j_label


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

    def _resolve_label(self, entity_type: str, entity_name: str) -> str:
        """Return the Neo4j label for a data entity based on entity_type."""
        return entity_type_to_neo4j_label(entity_type, entity_name)

    def _resolve_program_label(self, language: str) -> str:
        """Return the Neo4j label for a program node."""
        lang = language.upper()
        if lang == "COBOL":
            return "COBOLProgram"
        if lang == "JCL":
            return "JCLJob"
        if lang == "JAVA":
            return "JavaClass"
        if lang == "SQL":
            return "SQLProcedure"
        return "COBOLProgram"

    def upsert_lineage(self, openlineage_events: list[dict[str, Any]]) -> None:
        """Convert OpenLineage events to Neo4j nodes and edges.

        Uses entity_type facets to assign correct Neo4j labels (DB2Table,
        FlatFile, XMLFile, OracleTable, OracleView, etc.) instead of the
        generic File/Table labels.  Stores transformation_expression on
        MAPS_TO edges for frontend hover-state retrieval.

        Args:
            openlineage_events: List of OpenLineage RunEvent dicts.
        """
        for event in openlineage_events:
            job = event.get("job", {})
            job_name = job.get("name", "unknown")
            job_id = f"job_{job_name}"
            run_facets = event.get("run", {}).get("facets", {}).get("extractionConfig", {})
            language = run_facets.get("language", "")
            program_label = self._resolve_program_label(language)

            # Program / transformation node
            self.create_node(program_label, {
                "id": job_id,
                "name": job_name,
                "namespace": job.get("namespace", ""),
                "language": language,
                "confidence": run_facets.get("confidence", 0.0),
            })

            # Input dataset nodes + READS_FROM edges
            for inp in event.get("inputs", []):
                inp_name = inp.get("name", "unknown")
                inp_id = f"dataset_{inp_name}"
                inp_type = inp.get("entity_type") or inp.get("type", "")
                label = self._resolve_label(inp_type, inp_name)
                self.create_node(label, {
                    "id": inp_id,
                    "name": inp_name,
                    "namespace": inp.get("namespace", ""),
                    "system": inp.get("namespace", "").rstrip("://"),
                })
                self.create_edge(job_id, inp_id, "READS_FROM", {
                    "confidence": inp.get("confidence", 0.5),
                    "program": job_name,
                    "source_location": "",
                })

            # Output dataset nodes + WRITES_TO edges
            for out in event.get("outputs", []):
                out_name = out.get("name", "unknown")
                out_id = f"dataset_{out_name}"
                out_type = out.get("entity_type") or out.get("type", "")
                label = self._resolve_label(out_type, out_name)
                self.create_node(label, {
                    "id": out_id,
                    "name": out_name,
                    "namespace": out.get("namespace", ""),
                    "system": out.get("namespace", "").rstrip("://"),
                })
                self.create_edge(job_id, out_id, "WRITES_TO", {
                    "confidence": out.get("confidence", 0.5),
                    "program": job_name,
                    "source_location": "",
                })

                # Column-level lineage with transformation metadata for hover state
                col_lineage = out.get("facets", {}).get("columnLineage", {}).get("fields", {})
                for target_col, lineage_info in col_lineage.items():
                    tgt_col_id = f"col_{out_name}_{target_col}"
                    self.create_node("Column", {
                        "id": tgt_col_id,
                        "name": target_col,
                        "entity": out_name,
                        "entity_type": out_type,
                        "nullable": True,
                        "data_type": "unknown",
                    })
                    self.create_edge(out_id, tgt_col_id, "DEFINED_IN", {"entity": out_name, "position": 0})

                    for src_field in lineage_info.get("inputFields", []):
                        src_col_name = src_field.get("field", "")
                        src_tbl = src_field.get("dataset", "")
                        src_col_id = f"col_{src_tbl}_{src_col_name}"
                        self.create_node("Column", {
                            "id": src_col_id,
                            "name": src_col_name,
                            "entity": src_tbl,
                            "entity_type": inp_type if 'inp_type' in dir() else "",
                            "nullable": True,
                            "data_type": "unknown",
                        })
                        # Store transformation_expression on the edge for hover state
                        self.create_edge(src_col_id, tgt_col_id, "MAPS_TO", {
                            "mapping_type": lineage_info.get("transformationType", "UNKNOWN"),
                            "transformation_expression": lineage_info.get("transformationDescription", ""),
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


def fetch_all_column_lineage() -> dict[str, Any]:
    """Fetch COBOL/JCL/SQL column-level lineage aggregated by entity flow.

    Queries ColumnNode and TransformationStep nodes written by the extraction
    pipeline. Filters out Java transforms and self-loops. Returns entities
    (with their column lists) and flows (entity-to-entity connections with
    per-step column mapping details and code snippets).

    Returns:
        Dict with keys ``"entities"`` and ``"flows"``.
    """
    from neo4j import GraphDatabase
    from src.config import settings

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (src:ColumnNode)-[:TRANSFORMED_BY]->(t:TransformationStep)-[:PRODUCES]->(tgt:ColumnNode)
                WHERE src.file <> tgt.file
                RETURN
                  src.column_id        AS src_col_id,
                  src.name             AS src_col_name,
                  src.file             AS src_entity,
                  t.step_id            AS step_id,
                  t.name               AS transform_name,
                  t.type               AS transform_type,
                  t.language           AS language,
                  t.file_path          AS file_path,
                  coalesce(t.program_name, '') AS program_name,
                  t.code_snippet       AS code_snippet,
                  toFloat(t.confidence_score) AS confidence,
                  tgt.column_id        AS tgt_col_id,
                  tgt.name             AS tgt_col_name,
                  tgt.file             AS tgt_entity
                """
            )
            rows = [dict(r) for r in result]
    finally:
        driver.close()

    if not rows:
        return {"entities": [], "flows": []}

    def _is_java_name(name: str) -> bool:
        if not name:
            return False
        if re.match(r'^[a-z][a-zA-Z0-9_]*$', name):
            return True
        if '.' in name and not re.match(r'^[A-Z0-9][A-Z0-9_-]*$', name):
            return True
        return False

    def _is_java_path(s: str) -> bool:
        return '.java' in (s or '').lower() or '/java/' in (s or '').lower()

    def _keep_row(r: dict) -> bool:
        lang = r.get('language') or ''
        name = r.get('transform_name') or ''
        file_path = r.get('file_path') or ''
        src_e = r.get('src_entity') or ''
        tgt_e = r.get('tgt_entity') or ''
        if _is_java_path(src_e) or _is_java_path(tgt_e):
            return False
        if lang == 'sql' or file_path.lower().endswith('.sql'):
            return True
        if lang in ('cobol', 'jcl'):
            return True
        if lang == 'java' and _is_java_path(file_path):
            return False
        if re.match(r'^[A-Z0-9][A-Z0-9-]*$', name):
            return True
        if _is_java_name(name):
            return False
        return True

    rows = [r for r in rows if _keep_row(r)]
    if not rows:
        return {"entities": [], "flows": []}

    def _detect_lang(r: dict) -> str:
        lang = r.get('language') or ''
        if lang in ('cobol', 'jcl', 'sql'):
            return lang
        file_path = r.get('file_path') or ''
        if file_path.lower().endswith('.sql'):
            return 'sql'
        if file_path.lower().endswith('.jcl'):
            return 'jcl'
        return 'cobol'

    def _classify(name: str) -> tuple[str, str]:
        upper = name.upper()
        dot_count = name.count('.')
        if '(' in name:
            return 'z/OS', 'MainframeDataset'
        if upper.endswith('.XML') or '.XML.' in upper:
            return 'z/OS', 'XMLFile'
        if upper.startswith('BDD_NEPTUNE_DICC.') or upper.startswith('V_MI4014'):
            return 'Oracle', 'OracleTable'
        if upper.startswith('V_') and dot_count == 0:
            return 'Oracle', 'OracleView'
        if dot_count >= 2:
            return 'z/OS', 'MainframeDataset'
        if dot_count == 1:
            table_part = name.split('.', 1)[1].upper()
            if '_' in table_part:
                return 'DB2', 'DB2Table'
            return 'z/OS', 'MainframeDataset'
        flat_kw = {'FILE', 'EXTRACT', 'OUTPUT', 'INPUT', 'LOAD', 'REPORT', 'TRANS', 'REJECT', 'VALID'}
        if any(kw in upper for kw in flat_kw):
            return 'VSAM', 'MainframeDataset'
        if any(kw in upper for kw in ('_TABLE', '_LOG', '_MASTER', '_DATA', '_STG', '_DIARIAS', '_SUMMARY', '_DETAIL')):
            return 'Oracle', 'OracleTable'
        if upper.startswith('MONTHLY_') or upper.endswith('_REPORT') or upper.endswith('_VIEW'):
            return 'Oracle', 'OracleView'
        return 'VSAM', 'MainframeDataset'

    entity_cols: dict[str, set[str]] = {}
    for r in rows:
        if r.get('src_entity'):
            entity_cols.setdefault(r['src_entity'], set()).add(r['src_col_name'] or '')
        if r.get('tgt_entity'):
            entity_cols.setdefault(r['tgt_entity'], set()).add(r['tgt_col_name'] or '')

    flow_map: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        src_e = r.get('src_entity') or ''
        tgt_e = r.get('tgt_entity') or ''
        step_id = r.get('step_id') or ''
        key = (src_e, step_id, tgt_e)
        if key not in flow_map:
            prog_name = r.get('program_name') or r.get('transform_name') or ''
            flow_map[key] = {
                'id': step_id,
                'source_entity': src_e,
                'target_entity': tgt_e,
                'program_name': prog_name,
                'transform_name': r.get('transform_name') or prog_name,
                'program_type': _detect_lang(r),
                'transform_type': r.get('transform_type') or '',
                'code_snippet': r.get('code_snippet') or '',
                'file_path': r.get('file_path') or '',
                'confidence_score': r.get('confidence') or 0.5,
                'column_mappings': [],
            }
        flow_map[key]['column_mappings'].append({
            'source_col': r.get('src_col_name') or '',
            'target_col': r.get('tgt_col_name') or '',
            'transform_type': r.get('transform_type') or '',
            'snippet': r.get('code_snippet') or '',
        })

    entities = []
    for entity_name, cols in entity_cols.items():
        system, entity_type = _classify(entity_name)
        entity_id = 'entity_' + re.sub(r'[^a-z0-9]', '_', entity_name.lower())
        entities.append({
            'id': entity_id,
            'name': entity_name,
            'type': entity_type,
            'system': system,
            'columns': sorted(c for c in cols if c),
        })

    return {'entities': entities, 'flows': list(flow_map.values())}
