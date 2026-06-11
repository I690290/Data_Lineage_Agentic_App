"""Neo4j graph schema definitions for physical-entity data lineage storage."""
from __future__ import annotations


# ─── Node types ─────────────────────────────────────────────────────────────
# Physical data-storage entities
NODE_SCHEMAS: dict[str, list[str]] = {
    # Source/target data stores
    "DB2Table":      ["name", "schema_name", "database", "columns", "system"],
    "FlatFile":      ["name", "dsn", "lrecl", "format", "system"],
    "XMLFile":       ["name", "dsn", "schema_url", "system"],
    "OracleTable":   ["name", "schema_name", "database", "columns", "system"],
    "OracleView":    ["name", "schema_name", "definition", "system"],
    "ExternalTable": ["name", "schema_name", "access_driver", "location", "system"],

    # Transformation programs
    "COBOLProgram":  ["name", "program_id", "file_path", "division", "language"],
    "JCLJob":        ["name", "job_name", "class", "notify", "file_path"],
    "JCLStep":       ["name", "step_name", "program", "job_name", "sequence"],
    "DFSORTStep":    ["name", "step_name", "job_name", "operation"],
    "JavaClass":     ["name", "class_name", "package", "file_path", "language"],
    "SQLProcedure":  ["name", "file_path", "language"],

    # Column-level granularity
    "Column": ["name", "data_type", "entity", "entity_type", "nullable", "position"],
}

# ─── Edge types ─────────────────────────────────────────────────────────────
EDGE_SCHEMAS: dict[str, list[str]] = {
    # Entity-level flows (Program → DataStore)
    "READS_FROM": ["confidence", "dd_name", "source_location", "program"],
    "WRITES_TO":  ["confidence", "dd_name", "source_location", "program"],

    # Column-level flows — transformation_expression is the hover payload
    "MAPS_TO": [
        "mapping_type", "transformation_expression", "paragraph",
        "source_line", "confidence",
    ],

    # Structural
    "DEFINED_IN": ["entity", "position"],
    "EXECUTES":   ["step_name", "sequence"],
    "CALLS":      ["call_type", "source_location"],
    "JOINS_WITH": ["join_type", "join_condition"],

    # Cross-language
    "CROSS_LANGUAGE_LINK": ["confidence", "link_type", "evidence"],
}

# ─── Cypher constraints / indexes ────────────────────────────────────────────
CONSTRAINT_QUERIES: list[str] = [
    # Uniqueness constraints on physical entity nodes
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:DB2Table)      REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:OracleTable)   REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:OracleView)    REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:ExternalTable) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:FlatFile)      REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:XMLFile)       REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:COBOLProgram)  REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JCLJob)        REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JavaClass)     REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:SQLProcedure)  REQUIRE n.name IS UNIQUE",
    # Column uniqueness within its entity
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Column) REQUIRE (n.entity, n.name) IS UNIQUE",
    # Performance indexes
    "CREATE INDEX IF NOT EXISTS FOR (n:DB2Table)    ON (n.schema_name)",
    "CREATE INDEX IF NOT EXISTS FOR (n:OracleTable) ON (n.schema_name)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Column)      ON (n.data_type)",
    "CREATE INDEX IF NOT EXISTS FOR (n:JCLStep)     ON (n.job_name)",
]

# ─── entity_type string → Neo4j label mapping ────────────────────────────────
ENTITY_TYPE_TO_LABEL: dict[str, str] = {
    "DB2_TABLE":      "DB2Table",
    "FLAT_FILE":      "FlatFile",
    "XML_FILE":       "XMLFile",
    "ORACLE_TABLE":   "OracleTable",
    "ORACLE_VIEW":    "OracleView",
    "EXTERNAL_TABLE": "ExternalTable",
    "COBOL_PROGRAM":  "COBOLProgram",
    "JCL_JOB":        "JCLJob",
    "JCL_STEP":       "JCLStep",
    "JAVA_CLASS":     "JavaClass",
    "SQL_PROCEDURE":  "SQLProcedure",
    # OpenLineage namespace-based fallbacks
    "db2://":         "DB2Table",
    "oracle://":      "OracleTable",
    "file://":        "FlatFile",
    "xml://":         "XMLFile",
}


def entity_type_to_neo4j_label(entity_type: str, entity_name: str = "") -> str:
    """Resolve an entity_type string to the correct Neo4j label.

    Falls back to name-based heuristics when entity_type is unrecognised.
    """
    if entity_type in ENTITY_TYPE_TO_LABEL:
        return ENTITY_TYPE_TO_LABEL[entity_type]

    # Heuristic: classify from name
    upper = entity_name.upper()
    if upper.endswith(".XML") or ".XML." in upper:
        return "XMLFile"
    if upper.startswith("V_") or upper.endswith("_VIEW") or upper.startswith("V_MI4014"):
        return "OracleView"
    dot_count = entity_name.count(".")
    if dot_count >= 2 and "_" in entity_name:
        # three-qualifier mainframe DSN → FlatFile
        return "FlatFile"
    if dot_count == 1:
        schema, table = entity_name.split(".", 1)
        schema_upper = schema.upper()
        if schema_upper in ("CRISK", "DB2"):
            return "DB2Table"
        if schema_upper in ("BDD_NEPTUNE_DICC", "ORACLE"):
            return "OracleTable"
    return "FlatFile"  # safe default
