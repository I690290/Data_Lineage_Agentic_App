"""Strands Agents RAG layer for natural-language lineage queries."""
from __future__ import annotations

import json
from typing import Any

# ─── Neo4j schema reference ──────────────────────────────────────────────────
# Kept here so the system prompt and tool docstrings stay in sync.
_SCHEMA_SUMMARY = """
NODE LABELS (use exactly these in Cypher):
  Data stores  : DB2Table | FlatFile | XMLFile | OracleTable | OracleView | ExternalTable
  Programs     : COBOLProgram | JCLJob | JCLStep | DFSORTStep | JavaClass | SQLProcedure
  Column-level : Column

KEY PROPERTIES:
  All nodes      → name (str), id (str)
  DB2Table       → schema_name, system="DB2"
  OracleTable    → schema_name, system="oracle"
  OracleView     → schema_name, definition
  FlatFile       → dsn, lrecl
  XMLFile        → dsn
  ExternalTable  → schema_name, access_driver, location
  COBOLProgram   → program_id, file_path, language="cobol"
  JCLJob         → job_name, class, file_path
  Column         → name, entity (parent entity name), entity_type, data_type

RELATIONSHIPS (→ direction):
  (Program)  -[:READS_FROM]→  (DataStore)
  (Program)  -[:WRITES_TO]→   (DataStore)
  (DataStore)-[:DEFINED_IN]→  (Column)
  (Column)   -[:MAPS_TO]→     (Column)   # column-level lineage
               └ .transformation_expression  ← hover-state code snippet
               └ .mapping_type, .confidence

MI4014 WORKFLOW SUMMARY (Credit Risk Behaviour Scoring):
  CRISK.CUST_ACCOUNT_MASTER (DB2Table)
    → [CRDB2EXT COBOLProgram] → CRISK.BATCH.CUST.BHSCORE.EXTRACT (FlatFile)
      ← CRISK.DAILY_TRANSACTIONS (DB2Table)
    → [CRTXNEXT COBOLProgram] → CRISK.BATCH.TRANS.BHSCORE.EXTRACT (FlatFile)
    → [DFSORT JCLStep]        → CRISK.BATCH.MERGED.BHSCORE.EXTRACT (FlatFile)
    → [CRXMLGEN COBOLProgram] → NEPTUNE.FILES.LOAD.MI4014.XML (XMLFile)
    → [Oracle EXTERNAL TABLE] → BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_DIARIAS (ExternalTable)
    → [INSERT SQLProcedure]   → BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_STG (OracleTable)
    → [VIEW SQLProcedure]     → V_MI4014_TRANSACCIONES_VALIDAS (OracleView)
                              → V_MI4014_ACCOUNT_SUMMARY (OracleView)
                              → V_MI4014_LOAD_AUDIT (OracleView)
"""

_RAG_SYSTEM_PROMPT = f"""You are a data lineage expert for a Credit Risk ETL pipeline.
Answer questions about data flows, transformations, and dependencies in the codebase.

GRAPH SCHEMA:
{_SCHEMA_SUMMARY}

GUIDELINES:
- Use lineage_flow for standard lineage questions (upstream/downstream/column/transformation).
  Only use graph_traverse when lineage_flow cannot cover the specific query.
- When writing Cypher in graph_traverse, use the exact node labels listed above.
- Always cite the COBOL program name, JCL step, or SQL file that performs a transformation.
- For column-level questions, check the MAPS_TO edge's transformation_expression property —
  it contains the actual COBOL MOVE / SQL expression that produced the target column.
- For "what feeds into X?" questions: use lineage_flow with query_type="upstream".
- For "what does X produce/affect?" questions: use lineage_flow with query_type="downstream".
- For "how is column C populated?": use lineage_flow with query_type="column_lineage".
- For "show transformation logic for program P": use lineage_flow with query_type="transformation".
- Always give a human-readable narrative answer, not raw JSON.
"""


def _run_neo4j(cypher: str, params: dict | None = None) -> list[dict]:
    """Execute a Cypher query and return records as plain dicts."""
    from neo4j import GraphDatabase
    from src.config import settings

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            records = session.run(cypher, **(params or {}))
            return [dict(r) for r in records]
    finally:
        driver.close()


def _create_rag_agent() -> Any:
    """Build the Strands Agent with lineage-specific tools.

    Returns:
        Configured ``Agent`` instance, or a fallback stub if strands-agents
        is not installed.
    """
    try:
        from strands import Agent, tool
        from strands.models.bedrock import BedrockModel as StrandsBedrockModel

        from src.config import settings

        model = StrandsBedrockModel(
            model_id=settings.bedrock_text_model_id,
            region_name=settings.aws_region,
        )

        @tool
        def vector_search(query: str, language: str = "", top_k: int = 10) -> str:
            """Search the embedded code chunks for sections semantically related to the query.

            Use this to find the raw COBOL/SQL/JCL source code that implements a
            particular transformation or reads/writes a specific entity.
            """
            import chromadb
            from src.ingest import TitanEmbeddingFunction

            try:
                embed_fn = TitanEmbeddingFunction()
                client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
                collection = client.get_or_create_collection(
                    name="code_chunks",
                    embedding_function=embed_fn,
                    metadata={"hnsw:space": "cosine"},
                )
                where = {"language": language} if language else None
                results = collection.query(
                    query_texts=[query],
                    n_results=min(top_k, 10),
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
                items = []
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    items.append({
                        "file_path": meta.get("file_path", ""),
                        "language": meta.get("language", ""),
                        "ast_path": meta.get("ast_path", ""),
                        "relevance_score": round(1 - dist, 4),
                        "content_snippet": doc[:600],
                    })
                return json.dumps(items, indent=2)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def lineage_flow(
            query_type: str,
            entity: str = "",
            column: str = "",
            program: str = "",
            depth: int = 5,
        ) -> str:
            """Query data lineage from the Neo4j graph using pre-built patterns.

            query_type options:
              "upstream"        — all entities/programs that feed INTO entity
              "downstream"      — all entities/programs that entity feeds INTO
              "column_lineage"  — column-to-column mapping chain for entity.column
              "transformation"  — transformation expressions (code snippets) written
                                  by a program (hover-state data)
              "entity_columns"  — all columns defined on an entity (schema listing)
              "full_graph"      — summary of the entire lineage graph
              "programs"        — list all programs/jobs and their I/O entities
            """
            try:
                if query_type == "upstream":
                    rows = _run_neo4j(
                        f"MATCH path = (upstream)-[*1..{depth}]->(n {{name: $name}}) "
                        "RETURN [node IN nodes(path) | {name: node.name, labels: labels(node)}] AS chain",
                        {"name": entity},
                    )
                    return json.dumps(rows, indent=2, default=str)

                if query_type == "downstream":
                    rows = _run_neo4j(
                        f"MATCH path = (n {{name: $name}})-[*1..{depth}]->(downstream) "
                        "RETURN [node IN nodes(path) | {name: node.name, labels: labels(node)}] AS chain",
                        {"name": entity},
                    )
                    return json.dumps(rows, indent=2, default=str)

                if query_type == "column_lineage":
                    rows = _run_neo4j(
                        "MATCH (tgt:Column {entity: $entity, name: $col}) "
                        "<-[:MAPS_TO*1..8]-(src:Column) "
                        "RETURN src.entity AS source_entity, src.name AS source_column, "
                        "src.entity_type AS source_type",
                        {"entity": entity, "col": column},
                    )
                    return json.dumps(rows, indent=2, default=str)

                if query_type == "transformation":
                    # Return transformation_expression on MAPS_TO edges for a program
                    name_filter = program or entity
                    rows = _run_neo4j(
                        "MATCH (prog {name: $name})-[:WRITES_TO]->(tgt) "
                        "MATCH (src_col:Column)-[r:MAPS_TO]->(tgt_col:Column {entity: tgt.name}) "
                        "RETURN src_col.entity AS source_entity, src_col.name AS source_col, "
                        "tgt_col.name AS target_col, r.transformation_expression AS code_snippet, "
                        "r.mapping_type AS transform_type",
                        {"name": name_filter},
                    )
                    return json.dumps(rows, indent=2, default=str)

                if query_type == "entity_columns":
                    rows = _run_neo4j(
                        "MATCH (c:Column {entity: $entity}) "
                        "RETURN c.name AS column, c.data_type AS type, c.entity_type AS entity_type "
                        "ORDER BY c.name",
                        {"entity": entity},
                    )
                    return json.dumps(rows, indent=2, default=str)

                if query_type == "full_graph":
                    counts = _run_neo4j(
                        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count "
                        "ORDER BY count DESC"
                    )
                    edges = _run_neo4j(
                        "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count "
                        "ORDER BY count DESC"
                    )
                    return json.dumps({"node_counts": counts, "edge_counts": edges}, indent=2, default=str)

                if query_type == "programs":
                    rows = _run_neo4j(
                        "MATCH (p)-[r:READS_FROM|WRITES_TO]->(d) "
                        "RETURN p.name AS program, labels(p)[0] AS program_type, "
                        "type(r) AS operation, d.name AS entity, labels(d)[0] AS entity_type "
                        "ORDER BY p.name"
                    )
                    return json.dumps(rows, indent=2, default=str)

                return json.dumps({"error": f"Unknown query_type: '{query_type}'. "
                                             "Use: upstream, downstream, column_lineage, "
                                             "transformation, entity_columns, full_graph, programs"})
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def graph_traverse(cypher_query: str) -> str:
            """Execute a raw Cypher query on the Neo4j lineage graph.

            Use only when lineage_flow cannot express the needed query.
            Node labels: DB2Table, FlatFile, XMLFile, OracleTable, OracleView,
            ExternalTable, COBOLProgram, JCLJob, JCLStep, JavaClass, SQLProcedure, Column.
            Relationships: READS_FROM, WRITES_TO, MAPS_TO, DEFINED_IN, CROSS_LANGUAGE_LINK.
            """
            try:
                rows = _run_neo4j(cypher_query)
                return json.dumps(rows, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def code_lookup(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
            """Retrieve raw source code from a specific file and optional line range.

            Use this to show the exact COBOL MOVE, SQL INSERT, or JCL DD statement
            that implements a particular transformation.
            """
            from pathlib import Path
            try:
                p = Path(file_path)
                if not p.exists():
                    p = Path(settings.repo_path) / file_path
                if not p.exists():
                    return json.dumps({"error": f"File not found: {file_path}"})
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                if start_line > 0 or end_line > 0:
                    s = max(0, start_line - 1)
                    e = end_line if end_line > 0 else len(lines)
                    lines = lines[s:e]
                return json.dumps({"file_path": str(p), "content": "\n".join(lines)})
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def schema_lookup(entity_name: str) -> str:
            """Return all columns defined on a data entity (table, file, or view).

            Use this to understand the structure of DB2 tables, flat files, Oracle
            tables, or views before tracing column-level lineage.
            """
            try:
                rows = _run_neo4j(
                    "MATCH (c:Column {entity: $entity}) "
                    "RETURN c.name AS column, c.data_type AS data_type, "
                    "c.nullable AS nullable, c.entity_type AS entity_type "
                    "ORDER BY c.name",
                    {"entity": entity_name},
                )
                if not rows:
                    # Fallback: search by entity name fragment
                    rows = _run_neo4j(
                        "MATCH (c:Column) WHERE c.entity CONTAINS $fragment "
                        "RETURN c.entity AS entity, c.name AS column, c.data_type AS data_type "
                        "ORDER BY c.entity, c.name LIMIT 50",
                        {"fragment": entity_name},
                    )
                return json.dumps({"entity": entity_name, "columns": rows}, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def impact_analysis(entity_name: str) -> str:
            """Trace all downstream consumers of a given entity, column, or file.

            Returns the full downstream impact chain — which programs read it,
            what they write, and what downstream tables/views are ultimately affected.
            """
            try:
                rows = _run_neo4j(
                    "MATCH (n {name: $name})-[r*1..6]->(downstream) "
                    "RETURN downstream.name AS name, labels(downstream)[0] AS type, "
                    "length(r) AS hops "
                    "ORDER BY hops, name",
                    {"name": entity_name},
                )
                return json.dumps({"entity": entity_name, "downstream_impact": rows}, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return Agent(
            model=model,
            tools=[lineage_flow, vector_search, graph_traverse, code_lookup, schema_lookup, impact_analysis],
            system_prompt=_RAG_SYSTEM_PROMPT,
        )

    except ImportError:
        print("[strands_rag] strands-agents not installed — using stub RAG agent")
        return _StubRagAgent()


class _StubRagAgent:
    """Fallback stub when strands-agents is not installed."""

    def __call__(self, question: str) -> str:
        return (
            "strands-agents package is required for RAG queries. "
            "Install with: uv add strands-agents strands-agents-tools"
        )


class StrandsRAG:
    """Agentic RAG wrapper for the data lineage system.

    Uses model-driven tool selection (Strands Agents) to answer
    natural-language questions about the lineage graph.

    The RAG layer sits atop the populated ChromaDB + Neo4j stores.
    It is distinct from the extraction pipeline (LangGraph) and is
    used for interactive queries only.
    """

    def __init__(self) -> None:
        self._agent = _create_rag_agent()

    def query(self, question: str, history: list[dict] | None = None) -> str:
        """Answer a natural-language question about the lineage data.

        Prepends recent conversation history so follow-up questions work.

        Args:
            question: Natural language question.
            history: List of {role, content} dicts from prior turns.

        Returns:
            Agent response as a string.
        """
        full_prompt = question
        if history:
            turns = []
            for turn in history[-6:]:  # last 3 exchanges
                role = turn.get("role", "")
                content = turn.get("content", "")
                if role == "user":
                    turns.append(f"User: {content}")
                elif role == "assistant":
                    turns.append(f"Assistant: {content}")
            if turns:
                ctx = "\n".join(turns)
                full_prompt = f"[Previous conversation]\n{ctx}\n\n[Current question]\n{question}"

        try:
            result = self._agent(full_prompt)
            if hasattr(result, "message"):
                return str(result.message)
            return str(result)
        except Exception as exc:
            return f"RAG query error: {exc}"
