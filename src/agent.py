"""LangGraph agent pipeline for data lineage extraction."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from nodes.column_lineage_node import column_lineage_extraction_node
from src.config import settings
from src.ingest import chunk_file, walk_repo
from src.models import AgentState, AnalysisResult, LineageEdge, LineageNode
from src.neo4j_writer import write_column_lineage_to_neo4j, write_lineage_to_neo4j


_ANALYSIS_SYSTEM_PROMPT = """You are a data lineage expert. Analyse the provided source code chunk and extract data lineage information.

You MUST respond with ONLY a valid JSON object in exactly this format (no extra text before or after):
{
  "reads_from": ["<table_or_file_name>", ...],
  "writes_to": ["<table_or_file_name>", ...],
  "calls": ["<program_or_service_name>", ...],
  "transformations": ["<brief description of each transformation>", ...],
  "confidence": <float 0.0-1.0>
}

Rules:
- reads_from: all data sources READ by this code (tables, files, datasets, queues)
- writes_to: all data targets WRITTEN by this code (tables, files, datasets)
- calls: external programs, services, or stored procedures called
- transformations: brief plain-text description of each data transformation applied
- confidence: your confidence in the extraction (0.0 = no data, 1.0 = very clear)
- Use UPPERCASE for table/dataset names
- Include schema prefix if visible (e.g. CUSTSCHEMA.CUSTOMER_TABLE)
- If nothing is found, use empty lists and confidence 0.0
"""


def _make_llm(temperature: float = 0.0) -> ChatBedrockConverse:
    """Create the primary Bedrock text model client."""
    return ChatBedrockConverse(
        model=settings.bedrock_text_model_id,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token or None,
        temperature=temperature,
        max_tokens=4096,
    )


def _build_analysis_prompt(
    file_path: str,
    language: str,
    content: str,
    config_map: dict[str, str],
    jcl_dd_map: dict[str, str],
) -> str:
    """Build the analysis prompt for a source file."""
    config_ctx = json.dumps(config_map, indent=2) if config_map else '{}'
    jcl_ctx = json.dumps(jcl_dd_map, indent=2) if jcl_dd_map else '{}'
    truncated = content[:8000] + ('\n... [truncated]' if len(content) > 8000 else '')
    return f"""File: {file_path}
Language: {language}

Spring datasource config context (bean name → schema/table):
{config_ctx}

JCL DD name → physical dataset context:
{jcl_ctx}

Source code:
```
{truncated}
```

Extract the data lineage for this file. Return ONLY the JSON object."""


def _parse_application_yml(file_path: str) -> dict[str, str]:
    """Extract datasource bean to schema or table mappings from application.yml."""
    try:
        import yaml

        with open(file_path, 'r', encoding='utf-8') as handle:
            cfg = yaml.safe_load(handle)
        result: dict[str, str] = {}
        spring = cfg.get('spring', {}) or {}
        batch_cfg = cfg.get('batch', {}) or {}
        ds = spring.get('datasource', {}) or {}
        for ds_name, ds_props in ds.items():
            if isinstance(ds_props, dict) and 'schema' in ds_props:
                result[f'datasource.{ds_name}'] = ds_props['schema']
        for section_key, section_val in batch_cfg.items():
            if isinstance(section_val, dict):
                for key, value in section_val.items():
                    if key == 'table':
                        result[f'batch.{section_key}.table'] = str(value)
        return result
    except Exception:
        return {}


def _parse_jcl_dd_map(file_path: str) -> dict[str, str]:
    """Extract DDNAME to physical dataset mappings from a JCL file."""
    try:
        source = Path(file_path).read_text(encoding='utf-8', errors='replace')
        dd_map: dict[str, str] = {}
        for line in source.splitlines():
            if line.startswith('//*') or not line.startswith('//'):
                continue
            match = re.match(r'^//(\w+)\s+DD\s+.*DSN=([^\s,]+)', line)
            if match:
                dd_map[match.group(1)] = match.group(2).strip()
        return dd_map
    except Exception:
        return {}


def repo_scan_node(state: AgentState) -> AgentState:
    """Walk the repo and build a file manifest."""
    repo_path = state.get('repo_path', settings.repo_path)
    manifest = walk_repo(repo_path)
    print(f'[repo_scan] {len(manifest)} files found')
    return {**state, 'repo_path': repo_path, 'file_manifest': manifest, 'errors': [], 'unresolved_refs': []}


def config_resolve_node(state: AgentState) -> AgentState:
    """Parse config files and build config and JCL DD maps."""
    manifest = state.get('file_manifest', [])
    config_map: dict[str, str] = {}
    jcl_dd_map: dict[str, str] = {}
    for entry in manifest:
        lang = entry['language']
        file_path = entry['file_path']
        if lang == 'config':
            config_map.update(_parse_application_yml(file_path))
        elif lang == 'jcl':
            jcl_dd_map.update(_parse_jcl_dd_map(file_path))
    print(f'[config_resolve] {len(config_map)} config entries, {len(jcl_dd_map)} DD mappings')
    return {**state, 'config_map': config_map, 'jcl_dd_map': jcl_dd_map}


def _analyse_single_file(
    file_path: str,
    language: str,
    config_map: dict[str, str],
    jcl_dd_map: dict[str, str],
    llm: ChatBedrockConverse,
) -> AnalysisResult:
    """Analyse one source file and return structured lineage output."""
    chunks = chunk_file(file_path, language)
    if not chunks:
        return AnalysisResult(file_path=file_path, language=language, confidence=0.0, errors=['no chunks produced'])

    primary = next((chunk for chunk in chunks if chunk.chunk_type in ('program', 'file', 'job', 'class')), chunks[0])
    prompt = _build_analysis_prompt(file_path, language, primary.content, config_map, jcl_dd_map)
    try:
        response = llm.invoke([
            SystemMessage(content=_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        raw_content = response.content
        raw = raw_content if isinstance(raw_content, str) else str(raw_content)
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if not json_match:
            return AnalysisResult(
                file_path=file_path,
                language=language,
                confidence=0.0,
                raw_output=raw,
                errors=['no JSON found in response'],
            )
        data = json.loads(json_match.group(0))
        return AnalysisResult(
            file_path=file_path,
            language=language,
            reads_from=data.get('reads_from', []),
            writes_to=data.get('writes_to', []),
            calls=data.get('calls', []),
            transformations=data.get('transformations', []),
            confidence=float(data.get('confidence', 0.5)),
            raw_output=raw,
        )
    except Exception as exc:
        return AnalysisResult(file_path=file_path, language=language, confidence=0.0, errors=[str(exc)])


def code_analysis_node(state: AgentState) -> AgentState:
    """Run the primary LLM analysis on each non-config file."""
    manifest = state.get('file_manifest', [])
    config_map = state.get('config_map', {})
    jcl_dd_map = state.get('jcl_dd_map', {})
    llm = _make_llm()
    results: dict[str, AnalysisResult] = {}
    for entry in [item for item in manifest if item['language'] != 'config']:
        file_path = entry['file_path']
        language = entry['language']
        print(f'[code_analysis] Analysing {file_path} ({language})')
        result = _analyse_single_file(file_path, language, config_map, jcl_dd_map, llm)
        results[file_path] = result
        if result.errors:
            print(f'  [WARN] {result.errors}')
        else:
            print(f'  reads={result.reads_from}, writes={result.writes_to}, confidence={result.confidence}')
    return {**state, 'analysis_results': results}


def dependency_resolver_node(state: AgentState) -> AgentState:
    """Resolve cross-file program and dataset references."""
    results = state.get('analysis_results', {})
    manifest = state.get('file_manifest', [])
    jcl_dd_map = state.get('jcl_dd_map', {})
    unresolved: list[str] = []
    program_index = {Path(entry['file_path']).stem.upper(): entry['file_path'] for entry in manifest}
    resolved_results: dict[str, AnalysisResult] = {}
    for file_path, result in results.items():
        resolved_calls: list[str] = []
        for call_target in result.calls:
            name = call_target.upper()
            if name in program_index:
                resolved_calls.append(program_index[name])
            else:
                resolved_calls.append(call_target)
                unresolved.append(f'{file_path} → CALL {call_target}')
        resolved_results[file_path] = AnalysisResult(
            file_path=result.file_path,
            language=result.language,
            reads_from=[jcl_dd_map.get(item.upper(), item) for item in result.reads_from],
            writes_to=[jcl_dd_map.get(item.upper(), item) for item in result.writes_to],
            calls=resolved_calls,
            transformations=list(result.transformations),
            confidence=result.confidence,
            raw_output=result.raw_output,
            errors=list(result.errors),
        )
    print(f'[dep_resolver] {len(unresolved)} unresolved references')
    return {**state, 'analysis_results': resolved_results, 'unresolved_refs': unresolved}


def lineage_graph_builder_node(state: AgentState) -> AgentState:
    """Convert analysis results into lineage graph objects."""
    results = state.get('analysis_results', {})
    nodes: dict[str, LineageNode] = {}
    edges: list[LineageEdge] = []

    def _entity_id(name: str) -> str:
        return 'entity_' + re.sub(r'[^a-z0-9]', '_', name.lower())

    def _transform_id(file_path: str) -> str:
        return 'transform_' + re.sub(r'[^a-z0-9]', '_', Path(file_path).stem.lower())

    def _classify_entity(name: str) -> tuple[str, str, str]:
        """Return (system, entity_subtype, schema_name) using naming conventions.

        Classification priority:
        1. PDS member notation  e.g. PROD.PARMS(PROG001P)  → z/OS MainframeDataset
        2. .XML suffix or qualifier                         → z/OS XMLFile
        3. 3+ dot-qualified name e.g. CRISK.BATCH.X.Y      → z/OS MainframeDataset
        4. 2-part name SCHEMA.TABLE:
           - Underscore in table part → DB2 DB2Table
           - Otherwise               → z/OS MainframeDataset
        5. No dot, flat-file keywords (FILE/OUTPUT/INPUT…)  → VSAM MainframeDataset
        6. No dot, table-like keywords (_TABLE/_LOG/_MASTER) → DB2 DB2Table
        7. Default                                          → VSAM MainframeDataset
        """
        upper = name.upper()
        dot_count = name.count('.')
        schema = name.split('.')[0] if dot_count >= 1 else ''

        if '(' in name:
            return 'z/OS', 'MainframeDataset', schema
        if upper.endswith('.XML') or '.XML.' in upper:
            return 'z/OS', 'XMLFile', schema
        if dot_count >= 2:
            return 'z/OS', 'MainframeDataset', schema
        if dot_count == 1:
            table_part = name.split('.', 1)[1].upper()
            if '_' in table_part:
                return 'DB2', 'DB2Table', schema
            return 'z/OS', 'MainframeDataset', schema

        flat_file_kw = {'FILE', 'EXTRACT', 'OUTPUT', 'INPUT', 'LOAD', 'REPORT', 'TRANS', 'REJECT', 'VALID'}
        if any(kw in upper for kw in flat_file_kw):
            return 'VSAM', 'MainframeDataset', ''
        if any(kw in upper for kw in ('_TABLE', '_LOG', '_MASTER', '_DATA', '_DETAIL', '_SUMMARY')):
            return 'DB2', 'DB2Table', ''
        return 'VSAM', 'MainframeDataset', ''

    _TRANSFORM_SUBTYPE: dict[str, str] = {
        'cobol': 'COBOLProgram',
        'java':  'JavaClass',
        'jcl':   'JCLUtility',
    }

    def _get_or_create_entity(name: str) -> str:
        entity_id = _entity_id(name)
        if entity_id not in nodes:
            system, subtype, schema = _classify_entity(name)
            nodes[entity_id] = LineageNode(
                node_id=entity_id,
                label=name,
                node_type='DataEntity',
                entity_subtype=subtype,
                name=name,
                system=system,
                schema_name=schema,
            )
        return entity_id

    def _get_or_create_transform(file_path: str, language: str) -> str:
        transform_id = _transform_id(file_path)
        if transform_id not in nodes:
            nodes[transform_id] = LineageNode(
                node_id=transform_id,
                label=Path(file_path).stem.upper(),
                node_type='TransformationUnit',
                entity_subtype=_TRANSFORM_SUBTYPE.get(language, 'COBOLProgram'),
                name=Path(file_path).stem.upper(),
                system={'cobol': 'COBOL', 'java': 'Spring Batch', 'jcl': 'JCL'}.get(language, 'unknown'),
                file_path=file_path,
                language=language,
            )
        return transform_id

    for file_path, result in results.items():
        if result.confidence < 0.1 and not result.reads_from and not result.writes_to:
            continue
        transform_id = _get_or_create_transform(file_path, result.language)
        for source in result.reads_from:
            entity_id = _get_or_create_entity(source)
            edges.append(
                LineageEdge(
                    edge_id=f'e_{uuid.uuid4().hex[:8]}',
                    source_id=entity_id,
                    target_id=transform_id,
                    relationship='READS_FROM',
                )
            )
        for target in result.writes_to:
            entity_id = _get_or_create_entity(target)
            edges.append(
                LineageEdge(
                    edge_id=f'e_{uuid.uuid4().hex[:8]}',
                    source_id=transform_id,
                    target_id=entity_id,
                    relationship='WRITES_TO',
                )
            )
        for called in result.calls:
            called_transform_id = _transform_id(called)
            if called_transform_id in nodes or any(
                Path(entry['file_path']).stem.upper() == called.upper()
                for entry in state.get('file_manifest', [])
            ):
                edges.append(
                    LineageEdge(
                        edge_id=f'e_{uuid.uuid4().hex[:8]}',
                        source_id=transform_id,
                        target_id=called_transform_id,
                        relationship='TRANSFORMS_VIA',
                    )
                )
    print(f'[lineage_builder] {len(nodes)} nodes, {len(edges)} edges')
    return {**state, 'lineage_nodes': list(nodes.values()), 'lineage_edges': edges}


def validation_node(state: AgentState) -> AgentState:
    """Check for dangling edges and low-confidence analysis results."""
    node_ids = {node.node_id for node in state.get('lineage_nodes', [])}
    errors = list(state.get('errors', []))
    for edge in state.get('lineage_edges', []):
        if edge.source_id not in node_ids:
            errors.append(f'Dangling edge source: {edge.source_id} (edge {edge.edge_id})')
        if edge.target_id not in node_ids:
            errors.append(f'Dangling edge target: {edge.target_id} (edge {edge.edge_id})')
    low_conf = [file_path for file_path, result in state.get('analysis_results', {}).items() if 0 < result.confidence < 0.4]
    if low_conf:
        errors.append(f'Low-confidence analysis (<0.4) for: {low_conf}')
    print(f'[validation] {len(errors)} issue(s) found')
    for error in errors:
        print(f'  [!] {error}')
    return {**state, 'errors': errors}


def output_node(state: AgentState) -> AgentState:
    """Write lineage outputs to Neo4j and JSON."""
    nodes = state.get('lineage_nodes', [])
    edges = state.get('lineage_edges', [])
    errors = list(state.get('errors', []))
    try:
        write_lineage_to_neo4j(nodes, edges)
        print(f'[output] Written to Neo4j: {len(nodes)} nodes, {len(edges)} edges')
    except Exception as exc:
        print(f'[output] Neo4j write failed (continuing): {exc}')
        errors.append(f'Neo4j write error: {exc}')

    column_records = state.get('column_lineage_records', [])
    if column_records:
        try:
            write_column_lineage_to_neo4j(column_records)
            print(f'[output] Written {len(column_records)} column lineage records to Neo4j')
        except Exception as exc:
            print(f'[output] Column lineage Neo4j write failed (continuing): {exc}')

    cyto_json = {
        'nodes': [
            {
                'data': {
                    'id': node.node_id,
                    'label': node.label,
                    'type': node.node_type,
                    'subtype': node.entity_subtype,
                    'system': node.system,
                    'name': node.name,
                    'schema_name': node.schema_name,
                    'file_path': node.file_path,
                    'language': node.language,
                }
            }
            for node in nodes
        ],
        'edges': [
            {
                'data': {
                    'id': edge.edge_id,
                    'source': edge.source_id,
                    'target': edge.target_id,
                    'label': edge.relationship,
                }
            }
            for edge in edges
        ],
    }
    out_path = settings.lineage_json_path
    Path(out_path).write_text(json.dumps(cyto_json, indent=2), encoding='utf-8')
    print(f'[output] Lineage JSON written to {out_path}')
    return {**state, 'errors': errors, 'output_json_path': out_path}


def build_graph() -> StateGraph:
    """Compile the LangGraph pipeline."""
    graph = StateGraph(AgentState)
    graph.add_node('repo_scan', repo_scan_node)
    graph.add_node('config_resolve', config_resolve_node)
    graph.add_node('code_analysis', code_analysis_node)
    graph.add_node('column_lineage_extraction', column_lineage_extraction_node)
    graph.add_node('dependency_resolver', dependency_resolver_node)
    graph.add_node('lineage_graph_builder', lineage_graph_builder_node)
    graph.add_node('validation', validation_node)
    graph.add_node('output', output_node)
    graph.set_entry_point('repo_scan')
    graph.add_edge('repo_scan', 'config_resolve')
    graph.add_edge('config_resolve', 'code_analysis')
    graph.add_edge('code_analysis', 'column_lineage_extraction')
    graph.add_edge('column_lineage_extraction', 'dependency_resolver')
    graph.add_edge('dependency_resolver', 'lineage_graph_builder')
    graph.add_edge('lineage_graph_builder', 'validation')
    graph.add_edge('validation', 'output')
    graph.add_edge('output', END)
    return graph.compile()


def run_agent(repo_path: str | None = None) -> AgentState:
    """Execute the full lineage extraction pipeline."""
    compiled = build_graph()
    initial_state: AgentState = {
        'repo_path': repo_path or settings.repo_path,
        'file_manifest': [],
        'config_map': {},
        'jcl_dd_map': {},
        'analysis_results': {},
        'lineage_nodes': [],
        'lineage_edges': [],
        'unresolved_refs': [],
        'errors': [],
        'output_json_path': '',
        'column_lineage_records': [],
    }
    return compiled.invoke(initial_state)
