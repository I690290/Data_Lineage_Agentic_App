// Neo4j schema migration — adds column-level lineage support
// Safe to run multiple times (idempotent). Does NOT drop existing data.

// --- ColumnNode constraints and indexes ---
CREATE CONSTRAINT IF NOT EXISTS FOR (c:ColumnNode) REQUIRE c.column_id IS UNIQUE;
CREATE INDEX IF NOT EXISTS FOR (c:ColumnNode) ON (c.name);
CREATE INDEX IF NOT EXISTS FOR (c:ColumnNode) ON (c.file);

// --- TransformationStep constraints and indexes ---
CREATE CONSTRAINT IF NOT EXISTS FOR (t:TransformationStep) REQUIRE t.step_id IS UNIQUE;
CREATE INDEX IF NOT EXISTS FOR (t:TransformationStep) ON (t.name);
CREATE INDEX IF NOT EXISTS FOR (t:TransformationStep) ON (t.file_path);

// --- Relationship types (no DDL needed in Neo4j, documented here for reference) ---
// (ColumnNode)-[:TRANSFORMED_BY]->(TransformationStep)-[:PRODUCES]->(ColumnNode)
// (DataEntity)-[:HAS_COLUMN]->(ColumnNode)
