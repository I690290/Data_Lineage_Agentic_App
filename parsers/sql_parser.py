"""SQL parser using sqlglot for dialect-aware parsing and column lineage."""
from __future__ import annotations

import re
from typing import Any

from parsers.models import ChunkMetadata


def _try_import_sqlglot() -> Any:
    """Import sqlglot if available."""
    try:
        import sqlglot

        return sqlglot
    except ImportError:
        return None


_TABLE_PATTERN = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([\w.`\"]+)", re.IGNORECASE)
_COLUMN_PATTERN = re.compile(r"\bSELECT\s+(.*?)\s+FROM\b", re.IGNORECASE | re.DOTALL)


class SQLParser:
    """Parse SQL files into structural ChunkMetadata using sqlglot."""

    def __init__(self) -> None:
        self._sqlglot = _try_import_sqlglot()

    def parse(self, file_path: str, source_code: str, dialect: str = "db2") -> list[ChunkMetadata]:
        """Parse a SQL file into statement-level chunks.

        Args:
            file_path: Path to the SQL file.
            source_code: Raw SQL source text.
            dialect: sqlglot SQL dialect (``"db2"``, ``"oracle"``, ``"postgres"``).

        Returns:
            List of ChunkMetadata for each SQL statement.
        """
        if self._sqlglot:
            return self._parse_with_sqlglot(file_path, source_code, dialect)
        return self._parse_with_regex(file_path, source_code)

    def _parse_with_sqlglot(self, file_path: str, source_code: str, dialect: str) -> list[ChunkMetadata]:
        """Parse SQL using sqlglot AST."""
        sqlglot = self._sqlglot
        chunks: list[ChunkMetadata] = []
        try:
            statements = sqlglot.parse(source_code, dialect=dialect, error_level=sqlglot.ErrorLevel.IGNORE)
        except Exception:
            return self._parse_with_regex(file_path, source_code)

        cumulative_lines = 0
        for statement in statements:
            if statement is None:
                continue
            statement_sql = statement.sql(dialect=dialect)
            statement_type = type(statement).__name__.lower()
            structural_type = self._classify_statement_type(statement_type)
            start_line = cumulative_lines + 1
            end_line = start_line + statement_sql.count("\n")
            cumulative_lines = end_line

            chunk = ChunkMetadata(
                file_path=file_path,
                language="SQL",
                ast_path=f"{structural_type.upper()}.{self._get_stmt_name(statement)}",
                structural_type=structural_type,
                content=statement_sql,
                start_line=start_line,
                end_line=end_line,
            )
            chunk.io_operations = self._extract_io_operations(statement, statement_sql)
            chunk.data_movements = self._extract_column_lineage_sqlglot(statement, dialect)
            chunks.append(chunk)

        return chunks or self._parse_with_regex(file_path, source_code)

    def _parse_with_regex(self, file_path: str, source_code: str) -> list[ChunkMetadata]:
        """Regex-based fallback parser for SQL."""
        chunks: list[ChunkMetadata] = []
        statements = [statement.strip() for statement in re.split(r";\s*\n", source_code) if statement.strip()]
        line_offset = 1
        for statement in statements:
            statement_lower = statement[:30].lower().lstrip()
            if statement_lower.startswith("create table"):
                structural_type = "ddl_create_table"
            elif statement_lower.startswith("create view"):
                structural_type = "ddl_create_view"
            elif statement_lower.startswith("insert"):
                structural_type = "dml_insert"
            elif statement_lower.startswith("load"):
                structural_type = "dml_load"
            elif statement_lower.startswith("select"):
                structural_type = "dml_select"
            elif statement_lower.startswith("update"):
                structural_type = "dml_update"
            elif statement_lower.startswith("delete"):
                structural_type = "dml_delete"
            else:
                structural_type = "statement"

            end_line = line_offset + statement.count("\n")
            tables = [match.group(1) for match in _TABLE_PATTERN.finditer(statement)]
            chunk = ChunkMetadata(
                file_path=file_path,
                language="SQL",
                ast_path=structural_type.upper(),
                structural_type=structural_type,
                content=statement,
                start_line=line_offset,
                end_line=end_line,
            )
            chunk.io_operations = [{"type": "TABLE_REF", "target": table, "line": line_offset} for table in tables]
            chunks.append(chunk)
            line_offset = end_line + 1

        return chunks

    def _classify_statement_type(self, stmt_type: str) -> str:
        """Map sqlglot statement class name to structural type string."""
        mapping = {
            "create": "ddl_create_table",
            "drop": "ddl_drop",
            "alter": "ddl_alter",
            "select": "dml_select",
            "insert": "dml_insert",
            "update": "dml_update",
            "delete": "dml_delete",
            "merge": "dml_merge",
        }
        for key, value in mapping.items():
            if key in stmt_type:
                return value
        return "statement"

    def _get_stmt_name(self, stmt: Any) -> str:
        """Extract a meaningful name from a sqlglot statement node."""
        try:
            if hasattr(stmt, "this") and hasattr(stmt.this, "name"):
                return stmt.this.name or "unnamed"
        except Exception:
            pass
        return "unnamed"

    def _extract_io_operations(self, stmt: Any, sql_text: str) -> list[dict[str, object]]:
        """Extract table read/write operations from a statement."""
        _ = stmt
        return [
            {"type": "TABLE_REF", "target": match.group(1).strip("`\""), "line": 0}
            for match in _TABLE_PATTERN.finditer(sql_text)
        ]

    def _extract_column_lineage_sqlglot(self, stmt: Any, dialect: str) -> list[dict[str, object]]:
        """Use sqlglot.lineage() to extract column-level lineage."""
        sqlglot = self._sqlglot
        if sqlglot is None:
            return []
        try:
            sql_text = stmt.sql(dialect=dialect)
            if not re.search(r"\bSELECT\b", sql_text, re.IGNORECASE):
                return []
            column_match = _COLUMN_PATTERN.search(sql_text)
            if not column_match:
                return []
            column_list = [column.strip() for column in column_match.group(1).split(",")]
            movements: list[dict[str, object]] = []
            for column in column_list[:10]:
                column_name = column.split()[-1].strip("`\"")
                try:
                    node = sqlglot.lineage.lineage(column_name, sql_text, dialect=dialect)
                    if node and node.downstream:
                        for dependency in node.downstream:
                            movements.append(
                                {
                                    "source": str(dependency.name),
                                    "target": column_name,
                                    "type": "SQL_LINEAGE",
                                    "line": 0,
                                }
                            )
                except Exception:
                    pass
            return movements
        except Exception:
            return []
