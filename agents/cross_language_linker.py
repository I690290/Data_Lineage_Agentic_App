"""Cross-language lineage linker — resolves data flows across JCL/COBOL/Java/SQL."""
from __future__ import annotations

import re
from typing import Any


class CrossLanguageLinker:
    """Resolve data lineage connections that cross language boundaries.

    The full end-to-end lineage path is::

        INPUT_FILE → [JCL] → [COBOL] → OUTPUT_FILE → [SQL/Java] → DATABASE_TABLE

    Linking is done by matching:
    - JCL ``//DD`` names to COBOL ``SELECT ... ASSIGN TO`` statements.
    - COBOL output file FDs to SQL ``LOAD DATA INFILE`` / ``INSERT FROM`` statements.
    - COBOL ``EXEC SQL`` table names to standalone SQL table names.
    - Java repository entity tables to SQL table definitions.

    Args:
        neo4j_driver: Optional connected Neo4j driver for graph-backed context.
        chromadb_client: Optional ChromaDB client for vector-backed context.
    """

    def __init__(
        self,
        neo4j_driver: Any | None = None,
        chromadb_client: Any | None = None,
    ) -> None:
        self._neo4j = neo4j_driver
        self._chroma = chromadb_client

    def link(
        self,
        all_assertions: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Produce cross-language linking edges from grouped assertion dicts.

        Args:
            all_assertions: Dict of ``{language: [assertion, ...]}``.

        Returns:
            List of cross-language linking assertion dicts in OpenLineage format.
        """
        jcl_dd_map = self._parse_jcl_dd_statements(all_assertions.get("jcl", []))
        cobol_file_map = self._resolve_cobol_file_assignments(all_assertions.get("cobol", []))
        sql_load_sources = self._extract_sql_load_sources(all_assertions.get("sql", []))
        java_table_refs = self._extract_java_table_refs(all_assertions.get("java", []))

        cross_links: list[dict[str, Any]] = []

        # Link 1: JCL DD → COBOL file assignment
        cross_links.extend(self._match_jcl_to_cobol(jcl_dd_map, cobol_file_map))

        # Link 2: COBOL output file → SQL load source
        cross_links.extend(self._match_file_flows(cobol_file_map, sql_load_sources))

        # Link 3: COBOL EXEC SQL → standalone SQL tables
        cross_links.extend(self._match_exec_sql_tables(all_assertions))

        # Link 4: Java entity → SQL table
        cross_links.extend(self._match_java_to_sql(java_table_refs, all_assertions.get("sql", [])))

        print(f"[cross_lang_linker] Produced {len(cross_links)} cross-language links")
        return cross_links

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_jcl_dd_statements(
        self,
        jcl_assertions: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Extract DD name → physical dataset name from JCL assertions."""
        dd_map: dict[str, str] = {}
        for assertion in jcl_assertions:
            src = assertion.get("source", {})
            tgt = assertion.get("target", {})
            # JCL assertions with type DD_STATEMENT carry dd_name metadata
            dd_name = assertion.get("dd_name") or src.get("dd_name", "")
            dsn = tgt.get("entity", "") or src.get("entity", "")
            if dd_name and dsn:
                dd_map[dd_name.upper()] = dsn
        return dd_map

    def _resolve_cobol_file_assignments(
        self,
        cobol_assertions: list[dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        """Build a map of COBOL logical file names to their DD names and FDs.

        Returns:
            Dict of ``{logical_name: {"dd_name": ..., "fd_name": ..., "file": ..., "operation": ...}}``.
        """
        file_map: dict[str, dict[str, str]] = {}
        for assertion in cobol_assertions:
            atype = assertion.get("type", "")
            if "IO" in atype.upper() or "READ" in str(assertion).upper() or "WRITE" in str(assertion).upper():
                src = assertion.get("source", {})
                tgt = assertion.get("target", {})
                entity = src.get("entity") or tgt.get("entity", "")
                op_type = assertion.get("transformation", {}).get("type", "")
                if entity:
                    file_map[entity.upper()] = {
                        "entity": entity,
                        "operation": op_type,
                        "file_path": assertion.get("_file_path", ""),
                    }
        return file_map

    def _extract_sql_load_sources(
        self,
        sql_assertions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract SQL LOAD DATA source file references."""
        load_sources: list[dict[str, Any]] = []
        for assertion in sql_assertions:
            atype = assertion.get("type", "").upper()
            expr = assertion.get("transformation", {}).get("expression", "").upper()
            if "LOAD" in atype or "LOAD" in expr or "INFILE" in expr:
                load_sources.append({
                    "source_file": assertion.get("source", {}).get("entity", ""),
                    "target_table": assertion.get("target", {}).get("entity", ""),
                    "file_path": assertion.get("_file_path", ""),
                    "assertion": assertion,
                })
        return load_sources

    def _extract_java_table_refs(
        self,
        java_assertions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract Java entity → DB table references from Java assertions."""
        refs: list[dict[str, Any]] = []
        for assertion in java_assertions:
            atype = assertion.get("type", "").upper()
            if "ENTITY" in atype or "REPOSITORY" in atype or "JDBC" in atype:
                refs.append({
                    "table": assertion.get("source", {}).get("entity", "") or assertion.get("target", {}).get("entity", ""),
                    "file_path": assertion.get("_file_path", ""),
                    "assertion": assertion,
                })
        return refs

    def _match_jcl_to_cobol(
        self,
        jcl_dd_map: dict[str, str],
        cobol_file_map: dict[str, dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Create edges linking JCL DD statements to COBOL file assignments."""
        links: list[dict[str, Any]] = []
        for dd_name, dsn in jcl_dd_map.items():
            if dd_name in cobol_file_map:
                cobol_entry = cobol_file_map[dd_name]
                links.append({
                    "id": f"cross_{dd_name}_to_cobol",
                    "type": "CROSS_LANGUAGE_LINK",
                    "source": {"entity": dsn, "type": "jcl_dataset", "dd_name": dd_name},
                    "target": {"entity": cobol_entry["entity"], "type": "cobol_file", "file": cobol_entry.get("file_path", "")},
                    "transformation": {"type": "JCL_DD_ASSIGNMENT", "expression": f"//DD {dd_name} DSN={dsn}", "line": 0},
                    "confidence": 0.95,
                    "evidence": f"JCL DD {dd_name} → DSN={dsn} matches COBOL file assignment {cobol_entry['entity']}",
                })
        return links

    def _match_file_flows(
        self,
        cobol_file_map: dict[str, dict[str, str]],
        sql_load_sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Match COBOL output files to SQL load input files."""
        links: list[dict[str, Any]] = []
        for load in sql_load_sources:
            source_file = load.get("source_file", "").upper()
            for cobol_name, cobol_entry in cobol_file_map.items():
                # Fuzzy match on file stem or dataset name
                if (
                    source_file
                    and cobol_name
                    and (source_file in cobol_name or cobol_name in source_file)
                ):
                    links.append({
                        "id": f"cross_cobol_{cobol_name}_to_sql_{load['target_table']}",
                        "type": "CROSS_LANGUAGE_LINK",
                        "source": {"entity": cobol_name, "type": "cobol_output_file", "file": cobol_entry.get("file_path", "")},
                        "target": {"entity": load["target_table"], "type": "sql_table", "file": load.get("file_path", "")},
                        "transformation": {"type": "FILE_FLOW", "expression": f"COBOL writes {cobol_name} → SQL loads into {load['target_table']}", "line": 0},
                        "confidence": 0.85,
                        "evidence": f"COBOL output file '{cobol_name}' matches SQL LOAD source '{source_file}' → target '{load['target_table']}'",
                    })
        return links

    def _match_exec_sql_tables(
        self,
        all_assertions: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Match COBOL EXEC SQL table refs to standalone SQL table definitions."""
        links: list[dict[str, Any]] = []
        cobol_sql_tables: set[str] = set()
        for assertion in all_assertions.get("cobol", []):
            atype = assertion.get("type", "").upper()
            if "SQL" in atype or "EXEC" in str(assertion).upper():
                entity = assertion.get("source", {}).get("entity") or assertion.get("target", {}).get("entity", "")
                if entity:
                    cobol_sql_tables.add(entity.upper())

        sql_tables: dict[str, str] = {}  # table_name -> file_path
        for assertion in all_assertions.get("sql", []):
            entity = assertion.get("source", {}).get("entity") or assertion.get("target", {}).get("entity", "")
            if entity:
                sql_tables[entity.upper()] = assertion.get("_file_path", "")

        for cobol_table in cobol_sql_tables:
            if cobol_table in sql_tables:
                links.append({
                    "id": f"cross_cobol_sql_{cobol_table}",
                    "type": "CROSS_LANGUAGE_LINK",
                    "source": {"entity": cobol_table, "type": "cobol_exec_sql_table"},
                    "target": {"entity": cobol_table, "type": "sql_table", "file": sql_tables[cobol_table]},
                    "transformation": {"type": "EXEC_SQL_TABLE_MATCH", "expression": f"COBOL EXEC SQL references {cobol_table}", "line": 0},
                    "confidence": 0.9,
                    "evidence": f"COBOL EXEC SQL table '{cobol_table}' matches SQL definition in {sql_tables[cobol_table]}",
                })
        return links

    def _match_java_to_sql(
        self,
        java_table_refs: list[dict[str, Any]],
        sql_assertions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Link Java @Entity/@Repository table references to SQL DDL definitions."""
        links: list[dict[str, Any]] = []
        sql_table_set: dict[str, str] = {}
        for assertion in sql_assertions:
            for field in ("source", "target"):
                entity = assertion.get(field, {}).get("entity", "")
                if entity:
                    sql_table_set[entity.upper()] = assertion.get("_file_path", "")

        for ref in java_table_refs:
            table = ref.get("table", "").upper()
            if table and table in sql_table_set:
                links.append({
                    "id": f"cross_java_sql_{table}",
                    "type": "CROSS_LANGUAGE_LINK",
                    "source": {"entity": table, "type": "java_entity", "file": ref.get("file_path", "")},
                    "target": {"entity": table, "type": "sql_table", "file": sql_table_set[table]},
                    "transformation": {"type": "JAVA_ENTITY_MAP", "expression": f"Java @Entity maps to SQL table {table}", "line": 0},
                    "confidence": 0.9,
                    "evidence": f"Java entity '{table}' maps to SQL table defined in {sql_table_set[table]}",
                })
        return links
