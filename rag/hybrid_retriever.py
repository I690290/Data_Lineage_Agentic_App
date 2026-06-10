"""
Hybrid RAG retriever — combines Neo4j graph retrieval with ChromaDB vector retrieval.
Re-ranking uses BM25 + cosine similarity + graph proximity (no LLM, no cross-encoder).
"""
from __future__ import annotations

import asyncio

import chromadb
from neo4j import GraphDatabase
from rank_bm25 import BM25Okapi

from models.lineage_models import RetrievedChunk
from src.config import settings
from src.ingest import TitanEmbeddingFunction


class HybridRetriever:
    """Retrieve and rerank graph and vector context for lineage questions."""

    def __init__(self) -> None:
        """Initialise embedding, ChromaDB collections, and known entities."""
        self._embed_fn = TitanEmbeddingFunction()
        self._chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._code_col = self._chroma_client.get_or_create_collection(
            name="code_chunks",
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._config_col = self._chroma_client.get_or_create_collection(
            name="config_mappings",
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._known_entities: list[str] = self._load_known_entities()

    def _load_known_entities(self) -> list[str]:
        """Load entity and transformation names from Neo4j."""
        driver = None
        try:
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            with driver.session() as session:
                result = session.run(
                    "MATCH (n) WHERE n.name IS NOT NULL RETURN n.name AS name LIMIT 500"
                )
                return [rec["name"] for rec in result if rec["name"]]
        except Exception:
            return []
        finally:
            if driver is not None:
                driver.close()

    def _extract_entities_from_question(self, question: str) -> list[str]:
        """Extract likely entity names from a question.

        Args:
            question: The user question.

        Returns:
            Matched entity names.
        """
        found: list[str] = []
        q_upper = question.upper()
        for entity_name in self._known_entities:
            if entity_name.upper() in q_upper:
                found.append(entity_name)

        try:
            import spacy

            nlp = spacy.load("en_core_web_sm")
            doc = nlp(question)
            for ent in doc.ents:
                if ent.label_ in ("ORG", "PRODUCT", "GPE", "WORK_OF_ART"):
                    found.append(ent.text)
        except Exception:
            pass

        return list(set(found)) if found else []

    async def _graph_retrieval(self, question: str) -> list[RetrievedChunk]:
        """Retrieve context from Neo4j graph data."""
        chunks: list[RetrievedChunk] = []
        entity_names = self._extract_entities_from_question(question)
        if not entity_names:
            entity_names = self._known_entities[:5]

        driver = None
        try:
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            with driver.session() as session:
                for entity_name in entity_names[:5]:
                    col_result = session.run(
                        """
                        MATCH (c:ColumnNode {name: $col})-[:TRANSFORMED_BY]->(t)-[:PRODUCES]->(o)
                        RETURN c.name AS src_col, t.name AS transform, t.code_snippet AS snippet,
                               o.name AS tgt_col, t.file_path AS file_path, t.type AS t_type
                        LIMIT 5
                        """,
                        col=entity_name,
                    )
                    for rec in col_result:
                        text = (
                            f"Column {rec['src_col']} → {rec['transform']} ({rec['t_type']}) → {rec['tgt_col']}\n"
                            f"Snippet: {rec['snippet']}"
                        )
                        chunks.append(
                            RetrievedChunk(
                                text=text,
                                source=rec["file_path"] or entity_name,
                                chunk_type="graph",
                                graph_proximity_score=1.0,
                                metadata={"entity": entity_name, "type": "column_lineage"},
                            )
                        )

                    entity_result = session.run(
                        """
                        MATCH (e:DataEntity {name: $entity})-[:HAS_COLUMN]->(c)
                        RETURN e.name AS entity_name, c.name AS col_name, c.file AS col_file
                        LIMIT 30
                        """,
                        entity=entity_name,
                    )
                    entity_rows = list(entity_result)
                    if entity_rows:
                        cols_text = ", ".join(r["col_name"] for r in entity_rows if r["col_name"])
                        chunks.append(
                            RetrievedChunk(
                                text=f"Entity {entity_name} has columns: {cols_text}",
                                source=entity_name,
                                chunk_type="graph",
                                graph_proximity_score=1.0,
                                metadata={"entity": entity_name, "type": "entity_columns"},
                            )
                        )

                    path_result = session.run(
                        """
                        MATCH path = (src:DataEntity)-[*1..4]->(tgt:DataEntity)
                        WHERE src.name IN $names
                        RETURN src.name AS src_name, tgt.name AS tgt_name, length(path) AS hops
                        LIMIT 10
                        """,
                        names=[entity_name],
                    )
                    for rec in path_result:
                        hops = rec["hops"] or 1
                        prox = 1.0 if hops == 1 else (0.5 if hops == 2 else 0.0)
                        chunks.append(
                            RetrievedChunk(
                                text=f"Data flows from {rec['src_name']} to {rec['tgt_name']} ({hops} hop(s))",
                                source=rec["src_name"],
                                chunk_type="graph",
                                graph_proximity_score=prox,
                                metadata={"entity": entity_name, "type": "lineage_path", "hops": hops},
                            )
                        )
        except Exception as exc:
            print(f"[hybrid_retriever] Graph retrieval error: {exc}")
        finally:
            if driver is not None:
                driver.close()

        return chunks

    async def _vector_retrieval(self, question: str, n_results: int = 15) -> list[RetrievedChunk]:
        """Retrieve context from ChromaDB vector collections."""
        chunks: list[RetrievedChunk] = []
        try:
            code_results = self._code_col.query(
                query_texts=[question],
                n_results=min(n_results, 15),
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                code_results.get("documents", [[]])[0],
                code_results.get("metadatas", [[]])[0],
                code_results.get("distances", [[]])[0],
            ):
                vector_score = float(max(0.0, 1.0 - dist))
                chunks.append(
                    RetrievedChunk(
                        text=doc,
                        source=meta.get("file_path", "unknown"),
                        chunk_type="vector",
                        vector_score=vector_score,
                        metadata=dict(meta),
                    )
                )

            config_results = self._config_col.query(
                query_texts=[question],
                n_results=5,
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                config_results.get("documents", [[]])[0],
                config_results.get("metadatas", [[]])[0],
                config_results.get("distances", [[]])[0],
            ):
                vector_score = float(max(0.0, 1.0 - dist))
                chunks.append(
                    RetrievedChunk(
                        text=doc,
                        source=meta.get("file_path", "config"),
                        chunk_type="vector",
                        vector_score=vector_score,
                        metadata=dict(meta),
                    )
                )
        except Exception as exc:
            print(f"[hybrid_retriever] Vector retrieval error: {exc}")
        return chunks

    def _rerank(
        self,
        question: str,
        graph_chunks: list[RetrievedChunk],
        vector_chunks: list[RetrievedChunk],
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Re-rank chunks using BM25, vector, and graph proximity scores."""
        all_chunks = graph_chunks + vector_chunks
        seen: set[str] = set()
        deduped: list[RetrievedChunk] = []
        for chunk in all_chunks:
            key = f"{chunk.source}::{chunk.content_hash}"
            if key not in seen:
                seen.add(key)
                deduped.append(chunk)

        if not deduped:
            return []

        tokenised_corpus = [chunk.text.lower().split() for chunk in deduped]
        bm25 = BM25Okapi(tokenised_corpus)
        question_tokens = question.lower().split()
        bm25_scores = bm25.get_scores(question_tokens)
        max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
        normalised_bm25 = [score / max_bm25 for score in bm25_scores]

        for index, chunk in enumerate(deduped):
            chunk.bm25_score = float(normalised_bm25[index])
            chunk.final_score = (
                0.35 * chunk.bm25_score
                + 0.35 * chunk.vector_score
                + 0.30 * chunk.graph_proximity_score
            )

        deduped.sort(key=lambda chunk: chunk.final_score, reverse=True)
        return deduped[:top_k]

    async def retrieve(self, question: str, max_chunks: int = 8) -> list[RetrievedChunk]:
        """
        Run hybrid retrieval and return the top-ranked chunks.

        Args:
            question: The user question to retrieve context for.
            max_chunks: Maximum number of chunks to return (default 8).

        Returns:
            List of RetrievedChunk sorted by final_score descending.
        """
        graph_chunks, vector_chunks = await asyncio.gather(
            self._graph_retrieval(question),
            self._vector_retrieval(question),
        )
        return self._rerank(question, graph_chunks, vector_chunks, top_k=max_chunks)
