"""COBOL AST parser — regex-based with optional tree-sitter enhancement."""
from __future__ import annotations

import re

from parsers.models import ChunkMetadata


_DIVISION_PATTERN = re.compile(
    r"^[\s\d]*\s*(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION",
    re.MULTILINE | re.IGNORECASE,
)
_SECTION_PATTERN = re.compile(
    r"^\s{7,}(\S[\w-]*)\s+SECTION\s*\.",
    re.MULTILINE | re.IGNORECASE,
)
_PARAGRAPH_PATTERN = re.compile(
    r"^[\s\d]{6,8}([A-Z][\w-]{1,})\.\s*$",
    re.MULTILINE,
)
_FD_PATTERN = re.compile(r"^\s+FD\s+([\w-]+)", re.MULTILINE | re.IGNORECASE)
_SELECT_ASSIGN_PATTERN = re.compile(r"SELECT\s+([\w-]+)\s+ASSIGN\s+TO\s+([\w-]+)", re.IGNORECASE)
_MOVE_PATTERN = re.compile(
    r"MOVE\s+([\w-]+(?:\([\w\s,]+\))?)\s+TO\s+([\w-]+(?:\([\w\s,]+\))?)",
    re.IGNORECASE,
)
_READ_PATTERN = re.compile(r"\bREAD\s+([\w-]+)", re.IGNORECASE)
_WRITE_PATTERN = re.compile(r"\bWRITE\s+([\w-]+)", re.IGNORECASE)
_OPEN_PATTERN = re.compile(r"\bOPEN\s+(INPUT|OUTPUT|I-O|EXTEND)\s+([\w-]+)", re.IGNORECASE)
_COPY_PATTERN = re.compile(r"\bCOPY\s+([\w-]+)", re.IGNORECASE)
_PERFORM_PATTERN = re.compile(r"\bPERFORM\s+([\w-]+)", re.IGNORECASE)
_EXEC_SQL_PATTERN = re.compile(r"EXEC\s+SQL(.*?)END-EXEC", re.DOTALL | re.IGNORECASE)


class COBOLParser:
    """Parse COBOL source files into structural ChunkMetadata objects."""

    def parse(self, file_path: str, source_code: str) -> list[ChunkMetadata]:
        """Parse a COBOL source file.

        Args:
            file_path: Path to the COBOL file.
            source_code: Raw COBOL source text.

        Returns:
            List of ChunkMetadata objects for embedding.
        """
        lines = source_code.splitlines()
        chunks: list[ChunkMetadata] = []
        divisions = self._split_divisions(source_code)

        for div_name, div_content, div_start, div_end in divisions:
            if div_name == "IDENTIFICATION":
                chunks.append(self._make_chunk(file_path, div_content, div_start, div_end, "IDENTIFICATION", "division"))
            elif div_name == "ENVIRONMENT":
                chunks.append(self._make_chunk(file_path, div_content, div_start, div_end, "ENVIRONMENT", "division"))
            elif div_name == "DATA":
                chunks.extend(self._parse_data_division(file_path, div_content, div_start))
            elif div_name == "PROCEDURE":
                chunks.extend(self._parse_procedure_division(file_path, div_content, div_start))

        if not chunks:
            chunks.append(self._make_chunk(file_path, source_code, 1, len(lines), "ROOT", "copybook"))

        return chunks

    def _split_divisions(self, source: str) -> list[tuple[str, str, int, int]]:
        """Split source into (division_name, content, start_line, end_line) tuples."""
        matches = list(_DIVISION_PATTERN.finditer(source))
        result: list[tuple[str, str, int, int]] = []
        for index, match in enumerate(matches):
            div_name = match.group(1).upper()
            start_pos = match.start()
            end_pos = matches[index + 1].start() if index + 1 < len(matches) else len(source)
            div_content = source[start_pos:end_pos]
            start_line = source[:start_pos].count("\n") + 1
            end_line = source[:end_pos].count("\n") + 1
            result.append((div_name, div_content, start_line, end_line))
        return result

    def _parse_data_division(
        self, file_path: str, div_content: str, base_line: int
    ) -> list[ChunkMetadata]:
        """Parse DATA DIVISION into FD and 01-level chunks."""
        chunks: list[ChunkMetadata] = []
        for match in _FD_PATTERN.finditer(div_content):
            fd_name = match.group(1)
            start = div_content[:match.start()].count("\n")
            chunks.append(
                self._make_chunk(
                    file_path,
                    match.group(0),
                    base_line + start,
                    base_line + start + 2,
                    f"DATA.FD.{fd_name}",
                    "fd",
                )
            )
        if not chunks:
            chunks.append(
                self._make_chunk(
                    file_path,
                    div_content,
                    base_line,
                    base_line + div_content.count("\n"),
                    "DATA",
                    "division",
                )
            )
        return chunks

    def _parse_procedure_division(
        self, file_path: str, div_content: str, base_line: int
    ) -> list[ChunkMetadata]:
        """Parse PROCEDURE DIVISION into section and paragraph chunks."""
        chunks: list[ChunkMetadata] = []
        sections = list(_SECTION_PATTERN.finditer(div_content))
        if sections:
            for index, section_match in enumerate(sections):
                sec_name = section_match.group(1)
                start_pos = section_match.start()
                end_pos = sections[index + 1].start() if index + 1 < len(sections) else len(div_content)
                sec_content = div_content[start_pos:end_pos]
                start_line = base_line + div_content[:start_pos].count("\n")
                end_line = base_line + div_content[:end_pos].count("\n")
                chunk = self._make_chunk(
                    file_path,
                    sec_content,
                    start_line,
                    end_line,
                    f"PROCEDURE.{sec_name}",
                    "section",
                )
                chunk.io_operations = self._extract_io_operations(sec_content, start_line)
                chunk.data_movements = self._extract_data_movements(sec_content, start_line)
                chunks.append(chunk)
        else:
            paras = list(_PARAGRAPH_PATTERN.finditer(div_content))
            if paras:
                for index, para_match in enumerate(paras):
                    para_name = para_match.group(1)
                    start_pos = para_match.start()
                    end_pos = paras[index + 1].start() if index + 1 < len(paras) else len(div_content)
                    para_content = div_content[start_pos:end_pos]
                    start_line = base_line + div_content[:start_pos].count("\n")
                    end_line = base_line + div_content[:end_pos].count("\n")
                    chunk = self._make_chunk(
                        file_path,
                        para_content,
                        start_line,
                        end_line,
                        f"PROCEDURE.{para_name}",
                        "paragraph",
                    )
                    chunk.io_operations = self._extract_io_operations(para_content, start_line)
                    chunk.data_movements = self._extract_data_movements(para_content, start_line)
                    chunks.append(chunk)
            else:
                chunk = self._make_chunk(
                    file_path,
                    div_content,
                    base_line,
                    base_line + div_content.count("\n"),
                    "PROCEDURE",
                    "division",
                )
                chunk.io_operations = self._extract_io_operations(div_content, base_line)
                chunk.data_movements = self._extract_data_movements(div_content, base_line)
                chunks.append(chunk)
        return chunks

    def _extract_io_operations(self, content: str, base_line: int) -> list[dict[str, object]]:
        """Extract READ/WRITE/OPEN operations from a code block."""
        operations: list[dict[str, object]] = []
        for match in _READ_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": "READ", "target": match.group(1), "line": line})
        for match in _WRITE_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": "WRITE", "target": match.group(1), "line": line})
        for match in _OPEN_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            operations.append({"type": f"OPEN_{match.group(1).upper()}", "target": match.group(2), "line": line})
        return operations

    def _extract_data_movements(self, content: str, base_line: int) -> list[dict[str, object]]:
        """Extract MOVE statements as data movement records."""
        movements: list[dict[str, object]] = []
        for match in _MOVE_PATTERN.finditer(content):
            line = base_line + content[:match.start()].count("\n")
            movements.append(
                {
                    "source": match.group(1).strip(),
                    "target": match.group(2).strip(),
                    "type": "MOVE",
                    "line": line,
                }
            )
        return movements

    def _make_chunk(
        self,
        file_path: str,
        content: str,
        start_line: int,
        end_line: int,
        ast_path: str,
        structural_type: str,
    ) -> ChunkMetadata:
        """Create a ChunkMetadata for a structural block."""
        return ChunkMetadata(
            file_path=file_path,
            language="COBOL",
            ast_path=ast_path,
            structural_type=structural_type,
            content=content,
            start_line=start_line,
            end_line=end_line,
        )
