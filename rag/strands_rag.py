"""Strands Agents RAG layer for natural-language lineage queries."""
from __future__ import annotations

import json
from typing import Any


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
            """Search ChromaDB for code chunks semantically related to the query."""
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
                        "content_snippet": doc[:500],
                    })
                return json.dumps(items, indent=2)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def graph_traverse(cypher_query: str) -> str:
            """Execute a Cypher query on the Neo4j lineage graph."""
            try:
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
                with driver.session() as session:
                    records = session.run(cypher_query)
                    data = [dict(r) for r in records]
                driver.close()
                return json.dumps(data, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def code_lookup(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
            """Retrieve raw source code from a specific file and line range."""
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
        def schema_lookup(table_name: str) -> str:
            """Query column schemas for a given table from the lineage metadata."""
            try:
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
                with driver.session() as session:
                    records = session.run(
                        "MATCH (c:Column {table: $table}) RETURN c.name AS column, c.data_type AS type, c.nullable AS nullable",
                        table=table_name,
                    )
                    columns = [dict(r) for r in records]
                driver.close()
                return json.dumps({"table": table_name, "columns": columns})
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        @tool
        def impact_analysis(entity_name: str, entity_type: str = "column") -> str:
            """Trace all downstream consumers of a given column, table, or file."""
            try:
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
                with driver.session() as session:
                    records = session.run(
                        "MATCH (n {name: $name})-[*1..5]->(downstream) "
                        "RETURN downstream.name AS name, labels(downstream)[0] AS type",
                        name=entity_name,
                    )
                    downstream = [dict(r) for r in records]
                driver.close()
                return json.dumps({"entity": entity_name, "downstream_impact": downstream})
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return Agent(
            model=model,
            tools=[vector_search, graph_traverse, code_lookup, schema_lookup, impact_analysis],
            system_prompt="""You are a data lineage expert for legacy enterprise systems.
Answer questions about data flows, transformations, and dependencies in the codebase.
Always cite specific files, line numbers, and transformation logic in your answers.
Use graph_traverse for lineage tracing and vector_search for finding related code.
When asked about a specific table or column, use schema_lookup first, then graph_traverse
for lineage. For impact analysis (what depends on X?), use impact_analysis.""",
        )

    except ImportError:
        print("[strands_rag] strands-agents not installed — using stub RAG agent")
        return _StubRagAgent()


class _StubRagAgent:
    """Fallback stub when strands-agents is not installed."""

    def __call__(self, question: str) -> str:
        """Return a message indicating strands-agents is needed.

        Args:
            question: The user's natural language question.

        Returns:
            Error message string.
        """
        return (
            "strands-agents package is required for RAG queries. "
            "Install with: uv add strands-agents strands-agents-tools"
        )


class StrandsRAG:
    """Agentic RAG wrapper for the data lineage system.

    Uses model-driven tool selection (Strands Agents) to answer
    natural-language questions about the lineage graph.

    The RAG layer sits *atop* the populated ChromaDB + Neo4j stores.
    It is distinct from the extraction pipeline (LangGraph) which is
    deterministic. This layer is used for interactive queries.
    """

    def __init__(self) -> None:
        self._agent = _create_rag_agent()

    def query(self, question: str) -> str:
        """Answer a natural-language question about the lineage data.

        Args:
            question: Natural language question (e.g.
                ``"What feeds into the MONTHLY_REPORT table?"``).

        Returns:
            Agent response as a string.
        """
        try:
            result = self._agent(question)
            if hasattr(result, "message"):
                return str(result.message)
            return str(result)
        except Exception as exc:
            return f"RAG query error: {exc}"
