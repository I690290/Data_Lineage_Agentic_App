"""Cross-language lineage linker — resolves data flows across JCL/COBOL/Java/SQL."""
from __future__ import annotations

import re
from typing import Any


_MI4014_DD_TO_DSN: dict[str, str] = {
    # JCL DD name → physical dataset name (MI4014 Credit Risk Behaviour Scoring)
    "BHSCOEXT": "CRISK.BATCH.CUST.BHSCORE.EXTRACT",
    "BHSCOTXN": "CRISK.BATCH.TRANS.BHSCORE.EXTRACT",
    "BHSCOMRG": "CRISK.BATCH.MERGED.BHSCORE.EXTRACT",
    "BHSCOXML": "NEPTUNE.FILES.LOAD.MI4014.XML",
    # CRDB2EXT input
    "CUSTMAST": "CRISK.CUST_ACCOUNT_MASTER",
    # CRTXNEXT input
    "TRANHIST": "CRISK.DAILY_TRANSACTIONS",
}

_MI4014_XML_TO_ORACLE: dict[str, str] = {
    # Oracle external table reads this file
    "NEPTUNE.FILES.LOAD.MI4014.XML": "BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_DIARIAS",
}


class CrossLanguageLinker:
    """Resolve data lineage connections that cross language boundaries.

    The full end-to-end lineage path is::

        DB2_TABLE → [COBOL] → FLAT_FILE → [JCL/DFSORT] → MERGED_FILE
                  → [COBOL] → XML_FILE → [Oracle External Table] → ORACLE_TABLE
                  → [Oracle INSERT] → ORACLE_STAGING → [Oracle VIEW] → ORACLE_VIEW

    Linking is done by:
    1. Applying the MI4014 DD-name→DSN dictionary for known DD names.
    2. Fuzzy-matching JCL DD names to COBOL SELECT…ASSIGN TO statements.
    3. Matching COBOL output file DSNs to SQL LOAD/INSERT source files.
    4. Matching COBOL EXEC SQL table refs to standalone SQL table definitions.
    5. Linking Java @Entity/@Repository table refs to SQL table definitions.

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

        # Link 5: XML file → Oracle external table (MI4014-specific)
        cross_links.extend(self._match_xml_to_oracle(all_assertions))

        print(f"[cross_lang_linker] Produced {len(cross_links)} cross-language links")
        return cross_links

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_jcl_dd_statements(
        self,
        jcl_assertions: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Extract DD name → physical dataset name from JCL assertions.

        Seeds the map with known MI4014 DD names before scanning assertions,
        so cross-language links are produced even when JCL extraction misses a DD.
        """
        dd_map: dict[str, str] = dict(_MI4014_DD_TO_DSN)  # seed with known mappings
        for assertion in jcl_assertions:
            src = assertion.get("source", {})
            tgt = assertion.get("target", {})
            dd_name = (
                assertion.get("dd_name")
                or src.get("dd_name", "")
                or tgt.get("dd_name", "")
            )
            dsn = src.get("entity", "") or tgt.get("entity", "")
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

    def _match_xml_to_oracle(
        self,
        all_assertions: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Link XML output files to Oracle external tables that read them.

        Uses the MI4014 XML→Oracle mapping and also scans SQL assertions for
        ORACLE_LOADER / EXTERNAL_TABLE references to the same XML DSN.
        """
        links: list[dict[str, Any]] = []
        # Collect XML file entities from COBOL/JCL assertions
        xml_entities: set[str] = set()
        for lang in ("cobol", "jcl"):
            for assertion in all_assertions.get(lang, []):
                for field in ("source", "target"):
                    etype = assertion.get(field, {}).get("entity_type", "")
                    name = assertion.get(field, {}).get("entity", "")
                    if etype == "XML_FILE" or (name and (name.upper().endswith(".XML") or ".XML." in name.upper())):
                        xml_entities.add(name)

        # Collect Oracle external table entities from SQL assertions
        ext_tables: set[str] = set()
        for assertion in all_assertions.get("sql", []):
            atype = assertion.get("type", "")
            etype = assertion.get("target", {}).get("entity_type", "")
            name = assertion.get("target", {}).get("entity", "")
            if atype in ("EXTERNAL_TABLE", "TABLE_CREATE") or etype == "EXTERNAL_TABLE":
                if name:
                    ext_tables.add(name)

        # Apply known dictionary first
        for xml_dsn, oracle_ext in _MI4014_XML_TO_ORACLE.items():
            links.append({
                "id": f"cross_xml_{xml_dsn}_to_{oracle_ext}",
                "type": "CROSS_LANGUAGE_LINK",
                "source": {"entity": xml_dsn, "entity_type": "XML_FILE"},
                "target": {"entity": oracle_ext, "entity_type": "EXTERNAL_TABLE"},
                "transformation": {
                    "type": "ORACLE_LOADER",
                    "expression": f"Oracle External Table reads {xml_dsn} via ORACLE_LOADER",
                    "line": 0,
                },
                "confidence": 0.98,
                "evidence": f"Known MI4014 XML→Oracle external table mapping",
            })

        # Fuzzy: any XML entity referencing an Oracle external table by name fragment
        for xml in xml_entities:
            for ext in ext_tables:
                xml_stem = re.sub(r"[^A-Z0-9]", "", xml.upper())
                ext_stem  = re.sub(r"[^A-Z0-9]", "", ext.upper())
                if xml_stem and ext_stem and (xml_stem in ext_stem or ext_stem in xml_stem):
                    link_id = f"cross_xml_{xml}_to_{ext}"
                    if not any(l["id"] == link_id for l in links):
                        links.append({
                            "id": link_id,
                            "type": "CROSS_LANGUAGE_LINK",
                            "source": {"entity": xml, "entity_type": "XML_FILE"},
                            "target": {"entity": ext, "entity_type": "EXTERNAL_TABLE"},
                            "transformation": {"type": "ORACLE_LOADER", "expression": f"Oracle External Table reads {xml}", "line": 0},
                            "confidence": 0.8,
                            "evidence": f"XML file '{xml}' fuzzy-matched to external table '{ext}'",
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
