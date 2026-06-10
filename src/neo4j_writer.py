"""Neo4j writer and query helpers for lineage visualisation."""
from __future__ import annotations

from neo4j import GraphDatabase

from src.config import settings
from src.models import LineageEdge, LineageNode

_UPSERT_NODE = """
MERGE (n {node_id: $node_id})
SET n:{node_type}
SET n += {
  node_id: $node_id,
  label: $label,
  node_type: $node_type,
  entity_subtype: $entity_subtype,
  name: $name,
  system: $system,
  schema_name: $schema_name,
  file_path: $file_path,
  language: $language
}
"""

_UPSERT_EDGE_TYPED = """
MATCH (src {{node_id: $source_id}})
MATCH (tgt {{node_id: $target_id}})
MERGE (src)-[r:{rel_type} {{edge_id: $edge_id}}]->(tgt)
SET r.relationship = $relationship
"""


def write_lineage_to_neo4j(nodes: list[LineageNode], edges: list[LineageEdge]) -> None:
    """Write lineage nodes and edges to Neo4j."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        with driver.session() as session:
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:DataEntity) REQUIRE n.node_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:TransformationUnit) REQUIRE n.node_id IS UNIQUE"
            )

            with session.begin_transaction() as tx:
                for node in nodes:
                    tx.run(
                        _UPSERT_NODE.replace('{node_type}', node.node_type),
                        node_id=node.node_id,
                        label=node.label,
                        node_type=node.node_type,
                        entity_subtype=node.entity_subtype,
                        name=node.name,
                        system=node.system,
                        schema_name=node.schema_name,
                        file_path=node.file_path,
                        language=node.language,
                    )
                tx.commit()

            with session.begin_transaction() as tx:
                for edge in edges:
                    rel_type = edge.relationship.replace('-', '_').upper()
                    tx.run(
                        _UPSERT_EDGE_TYPED.format(rel_type=rel_type),
                        edge_id=edge.edge_id,
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                        relationship=edge.relationship,
                    )
                tx.commit()
    finally:
        driver.close()


def fetch_full_lineage() -> dict:
    """Fetch the entire lineage graph in Cytoscape.js JSON format."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    cyto_nodes: list[dict] = []
    cyto_edges: list[dict] = []
    try:
        with driver.session() as session:
            node_result = session.run(
                "MATCH (n) WHERE n.node_id IS NOT NULL RETURN properties(n) AS props"
            )
            for record in node_result:
                props = dict(record['props'])
                cyto_nodes.append(
                    {
                        'data': {
                            'id': props.get('node_id', ''),
                            'label': props.get('label', ''),
                            'type': props.get('node_type', ''),
                            'subtype': props.get('entity_subtype', ''),
                            'system': props.get('system', ''),
                            'name': props.get('name', ''),
                            'schema_name': props.get('schema_name', ''),
                            'file_path': props.get('file_path', ''),
                            'language': props.get('language', ''),
                        }
                    }
                )

            edge_result = session.run(
                "MATCH (src)-[r]->(tgt) "
                "WHERE src.node_id IS NOT NULL AND tgt.node_id IS NOT NULL "
                "RETURN src.node_id AS source, tgt.node_id AS target, "
                "type(r) AS rel_type, r.edge_id AS edge_id"
            )
            for record in edge_result:
                cyto_edges.append(
                    {
                        'data': {
                            'id': record['edge_id'] or f"e_{record['source']}_{record['target']}",
                            'source': record['source'],
                            'target': record['target'],
                            'label': record['rel_type'],
                        }
                    }
                )
    finally:
        driver.close()
    return {'nodes': cyto_nodes, 'edges': cyto_edges}


def fetch_entity_subgraph(entity_name: str, depth: int = 3) -> dict:
    """Fetch a subgraph around a specific named entity."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    cyto_nodes: list[dict] = []
    cyto_edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()
    try:
        with driver.session() as session:
            result = session.run(
                f"MATCH path = (n {{name: $name}})-[*1..{depth}]-(m) RETURN path",
                name=entity_name,
            )
            for record in result:
                path = record['path']
                for node in path.nodes:
                    nid = node.get('node_id', '')
                    if nid and nid not in seen_nodes:
                        seen_nodes.add(nid)
                        cyto_nodes.append({'data': dict(node)})
                for rel in path.relationships:
                    eid = rel.get('edge_id', f"e_{rel.start_node['node_id']}_{rel.end_node['node_id']}")
                    if eid not in seen_edges:
                        seen_edges.add(eid)
                        cyto_edges.append(
                            {
                                'data': {
                                    'id': eid,
                                    'source': rel.start_node['node_id'],
                                    'target': rel.end_node['node_id'],
                                    'label': rel.type,
                                }
                            }
                        )
    finally:
        driver.close()
    return {'nodes': cyto_nodes, 'edges': cyto_edges}


def write_column_lineage_to_neo4j(records: list) -> None:
    """Write ColumnLineageRecord objects to Neo4j as column lineage nodes.

    Args:
        records: List of column lineage records.
    """
    if not records:
        return

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        with driver.session() as session:
            session.run(
                'CREATE CONSTRAINT IF NOT EXISTS FOR (c:ColumnNode) REQUIRE c.column_id IS UNIQUE'
            )
            session.run(
                'CREATE CONSTRAINT IF NOT EXISTS FOR (t:TransformationStep) REQUIRE t.step_id IS UNIQUE'
            )
            with session.begin_transaction() as tx:
                try:
                    for record in records:
                        import hashlib

                        src_col_id = 'col_' + hashlib.md5(
                            f"{record.source_file}::{record.source_column}".encode()
                        ).hexdigest()[:12]
                        tgt_col_id = 'col_' + hashlib.md5(
                            f"{record.target_file}::{record.target_column}".encode()
                        ).hexdigest()[:12]
                        step_id = 'step_' + hashlib.md5(
                            f"{record.transformation_name}::{record.source_file}".encode()
                        ).hexdigest()[:12]

                        tx.run(
                            """
                            MERGE (c:ColumnNode {column_id: $col_id})
                            SET c.name = $name, c.file = $file, c.data_type = 'unknown', c.position = 0
                            """,
                            col_id=src_col_id,
                            name=record.source_column,
                            file=record.source_file,
                        )
                        tx.run(
                            """
                            MERGE (c:ColumnNode {column_id: $col_id})
                            SET c.name = $name, c.file = $file, c.data_type = 'unknown', c.position = 0
                            """,
                            col_id=tgt_col_id,
                            name=record.target_column,
                            file=record.target_file,
                        )
                        tx.run(
                            """
                            MERGE (t:TransformationStep {step_id: $step_id})
                            SET t.name = $name, t.type = $type,
                                t.code_snippet = $snippet, t.file_path = $file_path,
                                t.language = $language,
                                t.program_name = $program_name,
                                t.confidence_score = $confidence,
                                t.low_confidence = $low_confidence
                            """,
                            step_id=step_id,
                            name=record.transformation_name,
                            type=record.transformation_type,
                            snippet=record.transformation_code_snippet,
                            file_path=record.program_file_path or record.source_file,
                            language=(
                                'cobol' if record.program_file_path.lower().endswith(('.cbl', '.cob'))
                                else 'jcl' if record.program_file_path.lower().endswith('.jcl')
                                else 'sql' if record.program_file_path.lower().endswith('.sql')
                                else 'java' if record.program_file_path.lower().endswith('.java')
                                else 'cobol'
                            ),
                            program_name=record.program_name or Path(record.program_file_path).stem.upper(),
                            confidence=record.confidence_score,
                            low_confidence=record.low_confidence,
                        )
                        tx.run(
                            """
                            MATCH (src:ColumnNode {column_id: $src_id})
                            MATCH (t:TransformationStep {step_id: $step_id})
                            MERGE (src)-[:TRANSFORMED_BY]->(t)
                            """,
                            src_id=src_col_id,
                            step_id=step_id,
                        )
                        tx.run(
                            """
                            MATCH (t:TransformationStep {step_id: $step_id})
                            MATCH (tgt:ColumnNode {column_id: $tgt_id})
                            MERGE (t)-[:PRODUCES]->(tgt)
                            """,
                            step_id=step_id,
                            tgt_id=tgt_col_id,
                        )
                    tx.commit()
                except Exception:
                    tx.rollback()
                    raise
    finally:
        driver.close()


def fetch_column_lineage(output_file: str) -> dict:
    """Fetch column-level lineage for a specific output file.

    Args:
        output_file: Output file or table name to search for.

    Returns:
        Cytoscape.js nodes and edges.
    """
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    cyto_nodes: list[dict] = []
    cyto_edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (src:ColumnNode)-[:TRANSFORMED_BY]->(t:TransformationStep)-[:PRODUCES]->(tgt:ColumnNode)
                WHERE tgt.file CONTAINS $output_file OR src.file CONTAINS $output_file
                RETURN src, t, tgt
                """,
                output_file=output_file,
            )
            for record in result:
                src_node = record['src']
                t_node = record['t']
                tgt_node = record['tgt']
                for node, role in ((src_node, 'source'), (t_node, 'transform'), (tgt_node, 'target')):
                    nid = node.get('column_id') or node.get('step_id', '')
                    if nid and nid not in seen_nodes:
                        seen_nodes.add(nid)
                        props = dict(node)
                        cyto_nodes.append(
                            {
                                'data': {
                                    'id': nid,
                                    'label': props.get('name', nid),
                                    'node_role': role,
                                    'file': props.get('file', props.get('file_path', '')),
                                    'code_snippet': props.get('code_snippet', ''),
                                    'transformation_type': props.get('type', ''),
                                    'confidence_score': props.get('confidence_score', 1.0),
                                    'low_confidence': props.get('low_confidence', False),
                                }
                            }
                        )
                src_id = src_node.get('column_id', '')
                step_id = t_node.get('step_id', '')
                tgt_id = tgt_node.get('column_id', '')
                e1 = f'{src_id}__{step_id}'
                if e1 not in seen_edges:
                    seen_edges.add(e1)
                    cyto_edges.append(
                        {
                            'data': {
                                'id': e1,
                                'source': src_id,
                                'target': step_id,
                                'label': t_node.get('type', 'TRANSFORMED_BY'),
                            }
                        }
                    )
                e2 = f'{step_id}__{tgt_id}'
                if e2 not in seen_edges:
                    seen_edges.add(e2)
                    cyto_edges.append(
                        {
                            'data': {
                                'id': e2,
                                'source': step_id,
                                'target': tgt_id,
                                'label': 'PRODUCES',
                            }
                        }
                    )
    finally:
        driver.close()
    return {'nodes': cyto_nodes, 'edges': cyto_edges}


def fetch_all_column_lineage() -> dict:
    """Fetch COBOL/JCL-only column-level lineage aggregated by entity flow.

    Filters applied:
    - Skips Java transforms (detected by name pattern or stored language).
    - Skips self-loops (source_entity == target_entity).
    - Skips entities that are Java source file paths.

    Returns:
        Dict with keys 'entities' and 'flows' (entity-to-entity with column mappings).
    """
    from neo4j import GraphDatabase as _GDB
    from src.config import settings as _s
    import re as _re

    driver = _GDB.driver(_s.neo4j_uri, auth=(_s.neo4j_user, _s.neo4j_password))
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
        """Return True if transform name looks like a Java method/class."""
        if not name:
            return False
        # Java indicators: camelCase (starts lowercase), Class.method, or known Java terms
        if _re.match(r'^[a-z][a-zA-Z0-9_]*$', name):
            return True
        if '.' in name and not _re.match(r'^[A-Z0-9][A-Z0-9_-]*$', name):
            return True
        return False

    def _is_java_path(s: str) -> bool:
        """Return True if a string is a Java source file path."""
        return '.java' in (s or '').lower() or '/java/' in (s or '').lower()

    def _is_cobol_jcl_row(r: dict) -> bool:
        """Keep row if its transform is COBOL, JCL, or Oracle SQL (not Java)."""
        lang = r.get('language') or ''
        name = r.get('transform_name') or ''
        file_path = r.get('file_path') or ''
        src_e = r.get('src_entity') or ''
        tgt_e = r.get('tgt_entity') or ''

        # Reject Java entity paths leaking as entity names
        if _is_java_path(src_e) or _is_java_path(tgt_e):
            return False
        # Accept Oracle SQL scripts (language stored as 'sql')
        if lang == 'sql' or file_path.lower().endswith('.sql'):
            return True
        # If language stored correctly (after pipeline fix), use it
        if lang in ('cobol', 'jcl'):
            return True
        if lang == 'java' and _is_java_path(file_path):
            return False
        # Legacy heuristic: COBOL paragraphs are ALL-CAPS + hyphens/digits
        if _re.match(r'^[A-Z0-9][A-Z0-9-]*$', name):
            return True
        if _is_java_name(name):
            return False
        return True  # include unknown / ambiguous

    rows = [r for r in rows if _is_cobol_jcl_row(r)]

    if not rows:
        return {"entities": [], "flows": []}

    # Determine program_type: use stored language if valid, else detect from file path / name
    def _detect_lang(r: dict) -> str:
        lang = r.get('language') or ''
        if lang in ('cobol', 'jcl', 'sql'):
            return lang
        file_path = r.get('file_path') or ''
        if file_path.lower().endswith('.sql'):
            return 'sql'
        if file_path.lower().endswith('.jcl'):
            return 'jcl'
        return 'cobol'  # default for uppercase-hyphenated paragraph names

    # Aggregate entity→columns
    entity_cols: dict[str, set[str]] = {}
    for r in rows:
        if r.get('src_entity'):
            entity_cols.setdefault(r['src_entity'], set()).add(r['src_col_name'] or '')
        if r.get('tgt_entity'):
            entity_cols.setdefault(r['tgt_entity'], set()).add(r['tgt_col_name'] or '')

    # Aggregate flows: key = (src_entity, step_id, tgt_entity)
    flow_map: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        src_e = r.get('src_entity') or ''
        tgt_e = r.get('tgt_entity') or ''
        step_id = r.get('step_id') or ''
        key = (src_e, step_id, tgt_e)
        if key not in flow_map:
            # program_name = file stem (e.g. CRDB2EXT), transform_name = paragraph/method
            prog_name = r.get('program_name') or r.get('transform_name') or ''
            flow_map[key] = {
                'id': step_id,
                'source_entity': src_e,
                'target_entity': tgt_e,
                'program_name': prog_name,           # e.g. CRDB2EXT or MI4014_EXT_TABLE
                'transform_name': r.get('transform_name') or prog_name,  # paragraph/step
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

    def _classify(name: str) -> tuple[str, str]:
        upper = name.upper()
        dot_count = name.count('.')
        if '(' in name:
            return 'z/OS', 'MainframeDataset'
        if upper.endswith('.XML') or '.XML.' in upper:
            return 'z/OS', 'XMLFile'
        # BDD_NEPTUNE_DICC schema = Oracle
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

    entities = []
    for entity_name, cols in entity_cols.items():
        system, entity_type = _classify(entity_name)
        entity_id = 'entity_' + _re.sub(r'[^a-z0-9]', '_', entity_name.lower())
        entities.append({
            'id': entity_id,
            'name': entity_name,
            'type': entity_type,
            'system': system,
            'columns': sorted(c for c in cols if c),
        })

    return {
        'entities': entities,
        'flows': list(flow_map.values()),
    }


def fetch_lineage_summary() -> dict:
    """Fetch summary counts for the lineage graph."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    summary: dict = {
        'entities': [],
        'entity_count': 0,
        'jobs': [],
        'job_count': 0,
        'cobol_programs': [],
        'cobol_count': 0,
        'input_files': [],
        'output_files': [],
        'input_count': 0,
        'output_count': 0,
    }
    try:
        with driver.session() as session:
            entities = [rec['name'] for rec in session.run('MATCH (n:DataEntity) RETURN n.name AS name') if rec['name']]
            summary['entities'] = sorted(set(entities))
            summary['entity_count'] = len(summary['entities'])

            jobs = [
                rec['name']
                for rec in session.run(
                    "MATCH (n:TransformationUnit) WHERE n.language = 'java' RETURN n.name AS name"
                )
                if rec['name']
            ]
            summary['jobs'] = sorted(set(jobs))
            summary['job_count'] = len(summary['jobs'])

            cobol = [
                rec['name']
                for rec in session.run(
                    "MATCH (n:TransformationUnit) WHERE n.language = 'cobol' RETURN n.name AS name"
                )
                if rec['name']
            ]
            summary['cobol_programs'] = sorted(set(cobol))
            summary['cobol_count'] = len(summary['cobol_programs'])

            summary['output_files'] = sorted(
                {rec['name'] for rec in session.run("MATCH (e:DataEntity)<-[:WRITES_TO]-() RETURN DISTINCT e.name AS name") if rec['name']}
            )
            summary['output_count'] = len(summary['output_files'])
            summary['input_files'] = sorted(
                {rec['name'] for rec in session.run("MATCH (e:DataEntity)-[:READS_FROM]->() RETURN DISTINCT e.name AS name") if rec['name']}
            )
            summary['input_count'] = len(summary['input_files'])
    finally:
        driver.close()
    return summary


def fetch_transformation_snippet(transformation_id: str) -> dict:
    """Fetch the code snippet for a TransformationStep node."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        with driver.session() as session:
            result = session.run(
                'MATCH (t:TransformationStep {step_id: $id}) RETURN t',
                id=transformation_id,
            )
            record = result.single()
            if not record:
                return {}
            props = dict(record['t'])
            return {
                'step_id': props.get('step_id', ''),
                'name': props.get('name', ''),
                'type': props.get('type', ''),
                'code_snippet': props.get('code_snippet', ''),
                'file_path': props.get('file_path', ''),
                'language': props.get('language', ''),
            }
    finally:
        driver.close()
