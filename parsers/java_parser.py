"""Java AST parser — tree-sitter-java with regex fallback."""
from __future__ import annotations

import re

from parsers.models import ChunkMetadata


_CLASS_PATTERN = re.compile(
    r"(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+)*"
    r"(?:class|interface|enum)\s+([\w<>]+)",
    re.MULTILINE,
)
_METHOD_PATTERN = re.compile(
    r"(?:@[\w()\s\"]+\n\s*)*"
    r"(?:public|protected|private|static|final|synchronized|native|abstract|\s)+"
    r"[\w<>\[\],\s]+\s+([\w]+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
    re.MULTILINE,
)
_ANNOTATION_PATTERN = re.compile(r"@([\w]+)(?:\([^)]*\))?")
_IMPORT_PATTERN = re.compile(r"^import\s+([\w.]+);", re.MULTILINE)
_JDBC_PATTERN = re.compile(
    r"\b(PreparedStatement|Statement|ResultSet|DriverManager\.getConnection|"
    r"jdbcTemplate\.|namedParameterJdbcTemplate\.)\b",
    re.IGNORECASE,
)
_FILE_IO_PATTERN = re.compile(r"\b(BufferedReader|FileInputStream|FileReader|Scanner|Files\.read)\b")
_SQL_IN_JAVA_PATTERN = re.compile(r'"(SELECT|INSERT|UPDATE|DELETE|MERGE)[^"]*"', re.IGNORECASE)
_QUERY_ANNOTATION = re.compile(r'@Query\s*\(\s*"([^"]+)"', re.DOTALL)


class JavaParser:
    """Parse Java source files into structural ChunkMetadata objects."""

    def parse(self, file_path: str, source_code: str) -> list[ChunkMetadata]:
        """Parse a Java source file.

        Args:
            file_path: Path to the Java file.
            source_code: Raw Java source text.

        Returns:
            List of ChunkMetadata objects for embedding.
        """
        lines = source_code.splitlines()
        chunks: list[ChunkMetadata] = []
        _imports = self._resolve_imports(source_code)

        class_matches = list(_CLASS_PATTERN.finditer(source_code))
        if not class_matches:
            return [
                ChunkMetadata(
                    file_path=file_path,
                    language="Java",
                    ast_path="ROOT",
                    structural_type="file",
                    content=source_code,
                    start_line=1,
                    end_line=len(lines),
                )
            ]

        for index, class_match in enumerate(class_matches):
            class_name = class_match.group(1)
            start_pos = class_match.start()
            end_pos = class_matches[index + 1].start() if index + 1 < len(class_matches) else len(source_code)
            class_content = source_code[start_pos:end_pos]
            start_line = source_code[:start_pos].count("\n") + 1
            end_line = source_code[:end_pos].count("\n") + 1

            class_chunk = ChunkMetadata(
                file_path=file_path,
                language="Java",
                ast_path=class_name,
                structural_type="class",
                content=class_content[:2000],
                start_line=start_line,
                end_line=end_line,
            )
            chunks.append(class_chunk)

            for method_match in _METHOD_PATTERN.finditer(class_content):
                method_name = method_match.group(1)
                method_start_pos = method_match.start()
                method_body = self._extract_method_body(class_content, method_match.end() - 1)
                method_content = class_content[method_start_pos : method_start_pos + len(method_body)]
                method_start_line = start_line + class_content[:method_start_pos].count("\n")
                method_end_line = method_start_line + method_content.count("\n")
                method_chunk = ChunkMetadata(
                    file_path=file_path,
                    language="Java",
                    ast_path=f"{class_name}.{method_name}",
                    structural_type="method",
                    content=method_content,
                    start_line=method_start_line,
                    end_line=method_end_line,
                    parent_chunk_id=class_chunk.chunk_id,
                )
                method_chunk.io_operations = self._extract_jdbc_operations(method_content, method_start_line)
                method_chunk.io_operations.extend(self._extract_file_io(method_content, method_start_line))
                chunks.append(method_chunk)

        return chunks

    def _extract_method_body(self, source: str, brace_pos: int) -> str:
        """Extract method body by matching braces."""
        depth = 0
        for index in range(brace_pos, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[brace_pos : index + 1]
        return source[brace_pos:]

    def _extract_jdbc_operations(self, content: str, base_line: int) -> list[dict[str, object]]:
        """Extract JDBC/SQL operations from method content."""
        operations: list[dict[str, object]] = []
        for match in _JDBC_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": "JDBC", "target": match.group(1), "line": line})
        for match in _SQL_IN_JAVA_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": "EMBEDDED_SQL", "target": match.group(0)[:80], "line": line})
        for match in _QUERY_ANNOTATION.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": "JPA_QUERY", "target": match.group(1)[:80], "line": line})
        return operations

    def _extract_file_io(self, content: str, base_line: int) -> list[dict[str, object]]:
        """Extract file I/O operations."""
        operations: list[dict[str, object]] = []
        for match in _FILE_IO_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": "FILE_IO", "target": match.group(1), "line": line})
        return operations

    def _resolve_imports(self, source: str) -> dict[str, str]:
        """Build a short_name -> fully_qualified map of imports."""
        imports: dict[str, str] = {}
        for match in _IMPORT_PATTERN.finditer(source):
            fully_qualified_name = match.group(1)
            short_name = fully_qualified_name.split(".")[-1]
            imports[short_name] = fully_qualified_name
        return imports
