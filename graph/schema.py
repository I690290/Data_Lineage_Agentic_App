"""Neo4j graph schema definitions for data lineage storage."""
from __future__ import annotations


# Node types with required properties
NODE_SCHEMAS: dict[str, list[str]] = {
    "File": ["name", "path", "type", "language"],
    "Database": ["name", "host", "type"],
    "Table": ["name", "schema", "database", "columns"],
    "Column": ["name", "data_type", "table", "nullable"],
    "Program": ["name", "language", "file_path", "entry_point"],
    "Function": ["name", "program", "start_line", "end_line"],
    "Transformation": ["type", "expression", "source_location"],
    "Job": ["name", "type", "schedule"],
    "View": ["name", "schema", "definition"],
    "DataFile": ["name", "path", "format", "delimiter"],
}

# Edge types with required properties
EDGE_SCHEMAS: dict[str, list[str]] = {
    "READS_FROM": ["transformation_logic", "confidence", "source_location"],
    "WRITES_TO": ["transformation_logic", "confidence", "source_location"],
    "TRANSFORMS": ["expression", "type", "confidence"],
    "CALLS": ["call_type", "source_location"],
    "DEPENDS_ON": ["dependency_type"],
    "MAPS_TO": ["mapping_type", "expression", "confidence"],
    "EXECUTES": ["step_name", "source_location"],
    "LOADS_FROM": ["load_method", "delimiter", "source_location"],
    "DEFINED_IN": ["file_path", "start_line"],
    "JOINS_WITH": ["join_type", "join_condition"],
}

# Cypher constraint / index definitions for schema initialisation
CONSTRAINT_QUERIES: list[str] = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Table) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Column) REQUIRE (n.table, n.name) IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Program) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Job) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:File) REQUIRE n.path IS UNIQUE",
    "CREATE INDEX IF NOT EXISTS FOR (n:Table) ON (n.schema)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Column) ON (n.data_type)",
]
