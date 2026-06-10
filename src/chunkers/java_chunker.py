"""
Java chunker — uses tree-sitter to extract class-level and method-level chunks
from Java source files, with special attention to Spring Batch annotations.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.models import FileChunk

try:
    import tree_sitter_java as tsjava
    from tree_sitter import Language, Parser, Node

    JAVA_LANGUAGE = Language(tsjava.language())
    _TREE_SITTER_AVAILABLE = True
except Exception:
    _TREE_SITTER_AVAILABLE = False

# Spring Batch / data-access annotations that indicate data lineage relevance
_LINEAGE_ANNOTATIONS = {
    "Bean", "Component", "Repository", "Service",
    "EnableBatchProcessing", "Configuration",
    "Autowired", "Qualifier", "Value",
    "Primary", "Transactional",
    "ConfigurationProperties",
}

# Regex fallback for annotation extraction
_ANNOTATION_RE = re.compile(r"@(\w+)(?:\([^)]*\))?")
_CLASS_RE = re.compile(
    r"(?:public|private|protected)?\s*(?:class|interface|enum)\s+(\w+)",
)
_SQL_RE = re.compile(
    r'"([^"]*(?:SELECT|INSERT|UPDATE|DELETE|FROM|INTO|JOIN)[^"]*)"',
    re.IGNORECASE | re.DOTALL,
)
_TABLE_RE = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\b",
    re.IGNORECASE,
)
_DATASOURCE_BEAN_RE = re.compile(
    r"@ConfigurationProperties\s*\(\s*prefix\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


def _node_text(node: "Node", source_bytes: bytes) -> str:
    return source_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")


def _get_annotations(node: "Node", source_bytes: bytes) -> list[str]:
    annotations = []
    for child in node.children:
        if child.type == "modifiers":
            for mod in child.children:
                if mod.type == "marker_annotation" or mod.type == "annotation":
                    name_node = mod.child_by_field_name("name")
                    if name_node:
                        annotations.append(_node_text(name_node, source_bytes))
    return annotations


def _extract_sql_tables(text: str) -> dict[str, list[str]]:
    """Return {'reads': [...tables...], 'writes': [...tables...]} from SQL literals.
    Handles both single-line and multi-line string concatenation patterns.
    """
    reads: list[str] = []
    writes: list[str] = []

    # Collapse Java multi-line string concatenation into one pseudo-SQL string
    # Pattern: "..." + "..." + "..."  →  "......"
    collapsed = re.sub(r'"\s*\+\s*"', "", text)

    for sql_match in _SQL_RE.finditer(collapsed):
        sql = sql_match.group(1)
        for table_m in _TABLE_RE.finditer(sql):
            table = table_m.group(1).upper()
            if re.search(r"\bSELECT\b", sql, re.IGNORECASE):
                reads.append(table)
            if re.search(r"\b(INSERT|UPDATE)\b", sql, re.IGNORECASE):
                writes.append(table)

    # Also scan for schema-qualified SQL table references (SCHEMA.TABLE pattern).
    # Only match patterns that look like SQL identifiers: UPPERCASE_WITH_UNDERSCORES.NAME
    # (excludes Java package names which use camelCase / lowercase)
    for schema_tbl in re.finditer(
        r'\b([A-Z][A-Z0-9_]{2,}\.[A-Z][A-Z0-9_]{2,})\b', collapsed
    ):
        tbl = schema_tbl.group(1)
        # Must be all-uppercase to exclude Java class/package references
        if tbl != tbl.upper():
            continue
        # Must contain an underscore in at least one part (SQL naming convention)
        parts = tbl.split(".")
        if not any("_" in p for p in parts):
            continue
        # Classify as read or write based on nearby keyword
        context_start = max(0, schema_tbl.start() - 80)
        context = collapsed[context_start: schema_tbl.end() + 40]
        if re.search(r"\b(INSERT|UPDATE|MERGE)\b", context, re.IGNORECASE):
            writes.append(tbl)
        else:
            reads.append(tbl)

    return {"reads": list(set(reads)), "writes": list(set(writes))}


def _chunk_with_tree_sitter(file_path: str, source: str) -> list[FileChunk]:
    """Parse Java using tree-sitter AST."""
    parser = Parser(JAVA_LANGUAGE)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    chunks: list[FileChunk] = []

    def walk_classes(node: "Node") -> None:
        if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            class_name_node = node.child_by_field_name("name")
            class_name = _node_text(class_name_node, source_bytes) if class_name_node else "Unknown"
            annotations = _get_annotations(node, source_bytes)
            class_text = _node_text(node, source_bytes)
            sql_tables = _extract_sql_tables(class_text)
            ds_beans = _DATASOURCE_BEAN_RE.findall(class_text)

            chunks.append(FileChunk(
                file_path=file_path,
                language="java",
                chunk_type="class",
                chunk_name=class_name,
                content=class_text,
                metadata={
                    "annotations": annotations,
                    "sql_reads": sql_tables["reads"],
                    "sql_writes": sql_tables["writes"],
                    "datasource_prefixes": ds_beans,
                },
            ))

            # Walk methods inside the class
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_declaration":
                        method_name_node = child.child_by_field_name("name")
                        method_name = _node_text(method_name_node, source_bytes) if method_name_node else "unknown"
                        method_annotations = _get_annotations(child, source_bytes)
                        method_text = _node_text(child, source_bytes)
                        method_sql = _extract_sql_tables(method_text)

                        chunks.append(FileChunk(
                            file_path=file_path,
                            language="java",
                            chunk_type="method",
                            chunk_name=f"{class_name}::{method_name}",
                            content=method_text,
                            metadata={
                                "class_name": class_name,
                                "method_name": method_name,
                                "annotations": method_annotations,
                                "sql_reads": method_sql["reads"],
                                "sql_writes": method_sql["writes"],
                            },
                        ))
        for child in node.children:
            walk_classes(child)

    walk_classes(root)
    return chunks


def _chunk_with_regex(file_path: str, source: str) -> list[FileChunk]:
    """Regex-based fallback when tree-sitter is unavailable."""
    chunks: list[FileChunk] = []
    annotations = _ANNOTATION_RE.findall(source)
    sql_tables = _extract_sql_tables(source)
    class_m = _CLASS_RE.search(source)
    class_name = class_m.group(1) if class_m else Path(file_path).stem

    chunks.append(FileChunk(
        file_path=file_path,
        language="java",
        chunk_type="class",
        chunk_name=class_name,
        content=source,
        metadata={
            "annotations": annotations,
            "sql_reads": sql_tables["reads"],
            "sql_writes": sql_tables["writes"],
            "datasource_prefixes": _DATASOURCE_BEAN_RE.findall(source),
        },
    ))
    return chunks


def chunk_java_file(file_path: str) -> list[FileChunk]:
    """Parse a Java file and return a list of FileChunk objects."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")

    # Whole-file chunk always included
    whole_annotations = _ANNOTATION_RE.findall(source)
    whole_sql = _extract_sql_tables(source)
    whole_ds = _DATASOURCE_BEAN_RE.findall(source)

    whole_chunk = FileChunk(
        file_path=file_path,
        language="java",
        chunk_type="file",
        chunk_name=Path(file_path).stem,
        content=source,
        metadata={
            "annotations": list(set(whole_annotations)),
            "sql_reads": whole_sql["reads"],
            "sql_writes": whole_sql["writes"],
            "datasource_prefixes": whole_ds,
        },
    )

    if _TREE_SITTER_AVAILABLE:
        sub_chunks = _chunk_with_tree_sitter(file_path, source)
    else:
        sub_chunks = _chunk_with_regex(file_path, source)

    return [whole_chunk] + sub_chunks


def chunk_config_file(file_path: str) -> list[FileChunk]:
    """Parse application.yml or .properties into a config chunk."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    name = Path(file_path).name

    # Extract table/schema references from config values
    table_refs = re.findall(
        r"['\"]?([A-Z_][A-Z0-9_]*\.[A-Z_][A-Z0-9_]+)['\"]?",
        source,
        re.IGNORECASE,
    )

    return [FileChunk(
        file_path=file_path,
        language="config",
        chunk_type="config",
        chunk_name=name,
        content=source,
        metadata={"table_refs": table_refs},
    )]
