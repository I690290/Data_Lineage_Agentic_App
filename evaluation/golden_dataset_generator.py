from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parsers.cobol_parser import COBOLParser
from parsers.java_parser import JavaParser
from parsers.models import ChunkMetadata
from parsers.sql_parser import SQLParser

_COBOL_EXTENSIONS = {'.cbl', '.cob', '.cpy', '.copy'}
_JAVA_EXTENSIONS = {'.java'}
_SQL_EXTENSIONS = {'.sql', '.ddl', '.dml', '.psql'}
_COMPUTE_PATTERN = re.compile(r'\bCOMPUTE\s+([\w-]+)\s*=\s*(.+)', re.IGNORECASE)
_TABLE_PATTERN = re.compile(r'\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO|TABLE)\s+([\w.`"]+)', re.IGNORECASE)
_IDENTIFIER_PATTERN = re.compile(r'[A-Za-z_][\w$.-]*')


class GoldenDatasetGenerator:
    """Build deterministic golden lineage datasets from parser outputs.

    Args:
        cobol_parser: Parser used for COBOL sources.
        java_parser: Parser used for Java sources.
        sql_parser: Parser used for SQL sources.
    """

    def __init__(
        self,
        cobol_parser: COBOLParser | None = None,
        java_parser: JavaParser | None = None,
        sql_parser: SQLParser | None = None,
    ) -> None:
        self._cobol_parser = cobol_parser or COBOLParser()
        self._java_parser = java_parser or JavaParser()
        self._sql_parser = sql_parser or SQLParser()

    def generate_for_file(self, file_path: str) -> dict[str, Any]:
        """Generate deterministic ground-truth assertions for one source file.

        Args:
            file_path: Source file path.

        Returns:
            Golden dataset payload for that file.
        """
        source = Path(file_path).read_text(encoding='utf-8', errors='replace')
        language = self._detect_language(file_path)
        if language == 'COBOL':
            chunks = self._cobol_parser.parse(file_path, source)
            assertions = self._generate_cobol_assertions(file_path, source, chunks)
        elif language == 'Java':
            chunks = self._java_parser.parse(file_path, source)
            assertions = self._generate_java_assertions(file_path, chunks)
        elif language == 'SQL':
            chunks = self._sql_parser.parse(file_path, source)
            assertions = self._generate_sql_assertions(file_path, chunks)
        else:
            chunks = []
            assertions = []

        return {
            'file_path': file_path,
            'language': language,
            'chunk_count': len(chunks),
            'ground_truth_assertions': assertions,
            'ground_truth_cross_language': [
                assertion for assertion in assertions if assertion.get('cross_language', False)
            ],
            'generated_at': datetime.now(UTC).isoformat(),
        }

    def generate_for_directory(self, dir_path: str) -> list[dict[str, Any]]:
        """Generate golden datasets for all supported files in a directory.

        Args:
            dir_path: Root directory to scan recursively.

        Returns:
            List of golden dataset payloads.
        """
        results: list[dict[str, Any]] = []
        skip_dirs = {'.git', '.venv', '__pycache__', 'target', 'build', 'node_modules'}
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [directory for directory in dirs if directory not in skip_dirs]
            for file_name in sorted(files):
                file_path = os.path.join(root, file_name)
                language = self._detect_language(file_path)
                if language == 'unknown':
                    continue
                golden = self.generate_for_file(file_path)
                if golden['ground_truth_assertions']:
                    results.append(golden)
        return results

    def save(self, golden_data: list[dict[str, Any]], output_dir: str) -> None:
        """Persist generated golden datasets to disk.

        Args:
            golden_data: Generated golden dataset objects.
            output_dir: Output directory path.
        """
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        for item in golden_data:
            file_name = Path(item['file_path']).name
            output_path = destination / f'{file_name}.golden.json'
            output_path.write_text(json.dumps(item, indent=2), encoding='utf-8')

    def _generate_cobol_assertions(
        self,
        file_path: str,
        source: str,
        chunks: list[ChunkMetadata],
    ) -> list[dict[str, Any]]:
        """Extract MOVE, COMPUTE, READ, and WRITE assertions from COBOL."""
        assertions: list[dict[str, Any]] = []
        program_name = Path(file_path).stem
        seen: set[tuple[str, str, str, int]] = set()

        for chunk in chunks:
            for movement in chunk.data_movements:
                assertion = self._make_assertion(
                    source_entity=str(movement.get('source', '')),
                    source_column=str(movement.get('source', '')),
                    source_type='variable',
                    target_entity=str(movement.get('target', '')),
                    target_column=str(movement.get('target', '')),
                    target_type='variable',
                    transform_type=str(movement.get('type', 'MOVE')),
                    expression=f"{movement.get('type', 'MOVE')} {movement.get('source', '')} TO {movement.get('target', '')}",
                    line=int(movement.get('line', 0) or 0),
                    chunk=chunk,
                    file_path=file_path,
                    cross_language=False,
                )
                key = self._assertion_key(assertion)
                if key not in seen:
                    seen.add(key)
                    assertions.append(assertion)

            for io_operation in chunk.io_operations:
                op_type = str(io_operation.get('type', '')).upper()
                target = str(io_operation.get('target', ''))
                line = int(io_operation.get('line', 0) or 0)
                if 'READ' in op_type or 'OPEN_INPUT' in op_type:
                    assertion = self._make_assertion(
                        source_entity=target,
                        source_column='',
                        source_type='file',
                        target_entity=program_name,
                        target_column='',
                        target_type='program',
                        transform_type=op_type,
                        expression=f'{op_type} {target}',
                        line=line,
                        chunk=chunk,
                        file_path=file_path,
                        cross_language=False,
                    )
                elif 'WRITE' in op_type or 'OPEN_OUTPUT' in op_type:
                    assertion = self._make_assertion(
                        source_entity=program_name,
                        source_column='',
                        source_type='program',
                        target_entity=target,
                        target_column='',
                        target_type='file',
                        transform_type=op_type,
                        expression=f'{op_type} {target}',
                        line=line,
                        chunk=chunk,
                        file_path=file_path,
                        cross_language=False,
                    )
                else:
                    continue
                key = self._assertion_key(assertion)
                if key not in seen:
                    seen.add(key)
                    assertions.append(assertion)

        for match in _COMPUTE_PATTERN.finditer(source):
            target = match.group(1).strip()
            expression = match.group(2).strip().rstrip('.')
            line = source[:match.start()].count('\n') + 1
            source_terms = [
                term for term in _IDENTIFIER_PATTERN.findall(expression)
                if term.upper() != target.upper() and not term.isdigit()
            ]
            ast_chunk = self._chunk_for_line(chunks, line)
            for source_term in source_terms or [expression]:
                assertion = self._make_assertion(
                    source_entity=source_term,
                    source_column=source_term,
                    source_type='variable',
                    target_entity=target,
                    target_column=target,
                    target_type='variable',
                    transform_type='COMPUTE',
                    expression=expression,
                    line=line,
                    chunk=ast_chunk,
                    file_path=file_path,
                    cross_language=False,
                )
                key = self._assertion_key(assertion)
                if key not in seen:
                    seen.add(key)
                    assertions.append(assertion)

        return assertions

    def _generate_java_assertions(
        self,
        file_path: str,
        chunks: list[ChunkMetadata],
    ) -> list[dict[str, Any]]:
        """Extract JDBC, JPA, and file I/O assertions from Java parser output."""
        assertions: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, int]] = set()
        class_name = Path(file_path).stem

        for chunk in chunks:
            method_name = chunk.ast_path.split('.')[-1] if '.' in chunk.ast_path else class_name
            method_entity = chunk.ast_path
            for io_operation in list(chunk.io_operations):
                op_type = str(io_operation.get('type', '')).upper()
                target = str(io_operation.get('target', ''))
                line = int(io_operation.get('line', 0) or 0)

                if op_type in {'EMBEDDED_SQL', 'JPA_QUERY'}:
                    for table_name, direction in self._extract_sql_entities(target):
                        if direction == 'READ':
                            assertion = self._make_assertion(
                                source_entity=table_name,
                                source_column='',
                                source_type='table',
                                target_entity=method_entity,
                                target_column='',
                                target_type='method',
                                transform_type=op_type,
                                expression=target,
                                line=line,
                                chunk=chunk,
                                file_path=file_path,
                                cross_language=False,
                            )
                        else:
                            assertion = self._make_assertion(
                                source_entity=method_entity,
                                source_column='',
                                source_type='method',
                                target_entity=table_name,
                                target_column='',
                                target_type='table',
                                transform_type=op_type,
                                expression=target,
                                line=line,
                                chunk=chunk,
                                file_path=file_path,
                                cross_language=False,
                            )
                        key = self._assertion_key(assertion)
                        if key not in seen:
                            seen.add(key)
                            assertions.append(assertion)
                    continue

                if op_type == 'JDBC':
                    assertion = self._make_assertion(
                        source_entity=method_name,
                        source_column='',
                        source_type='method',
                        target_entity=target,
                        target_column='',
                        target_type='external_system',
                        transform_type=op_type,
                        expression=f'{method_name} uses {target}',
                        line=line,
                        chunk=chunk,
                        file_path=file_path,
                        cross_language=False,
                    )
                elif op_type == 'FILE_IO':
                    direction = 'READ' if any(token in target for token in ['Reader', 'Input', 'Scanner', 'read']) else 'WRITE'
                    if direction == 'READ':
                        assertion = self._make_assertion(
                            source_entity=target,
                            source_column='',
                            source_type='file',
                            target_entity=method_entity,
                            target_column='',
                            target_type='method',
                            transform_type='FILE_IO',
                            expression=f'{method_name} reads via {target}',
                            line=line,
                            chunk=chunk,
                            file_path=file_path,
                            cross_language=False,
                        )
                    else:
                        assertion = self._make_assertion(
                            source_entity=method_entity,
                            source_column='',
                            source_type='method',
                            target_entity=target,
                            target_column='',
                            target_type='file',
                            transform_type='FILE_IO',
                            expression=f'{method_name} writes via {target}',
                            line=line,
                            chunk=chunk,
                            file_path=file_path,
                            cross_language=False,
                        )
                else:
                    continue

                key = self._assertion_key(assertion)
                if key not in seen:
                    seen.add(key)
                    assertions.append(assertion)

        return assertions

    def _generate_sql_assertions(
        self,
        file_path: str,
        chunks: list[ChunkMetadata],
    ) -> list[dict[str, Any]]:
        """Extract column lineage assertions from SQL parser output."""
        assertions: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, int]] = set()

        for chunk in chunks:
            for movement in chunk.data_movements:
                source_entity, source_column = self._split_reference(str(movement.get('source', '')))
                target_entity, target_column = self._split_reference(str(movement.get('target', '')))
                assertion = self._make_assertion(
                    source_entity=source_entity,
                    source_column=source_column,
                    source_type='column',
                    target_entity=target_entity or source_entity,
                    target_column=target_column,
                    target_type='column',
                    transform_type=str(movement.get('type', 'SQL_LINEAGE')),
                    expression=chunk.content,
                    line=int(movement.get('line', chunk.start_line) or chunk.start_line),
                    chunk=chunk,
                    file_path=file_path,
                    cross_language=False,
                )
                key = self._assertion_key(assertion)
                if key not in seen:
                    seen.add(key)
                    assertions.append(assertion)

        return assertions

    def _make_assertion(
        self,
        *,
        source_entity: str,
        source_column: str,
        source_type: str,
        target_entity: str,
        target_column: str,
        target_type: str,
        transform_type: str,
        expression: str,
        line: int,
        chunk: ChunkMetadata | None,
        file_path: str,
        cross_language: bool,
    ) -> dict[str, Any]:
        """Create a canonical golden assertion payload."""
        return {
            'source': {
                'entity': source_entity,
                'column': source_column,
                'type': source_type,
            },
            'target': {
                'entity': target_entity,
                'column': target_column,
                'type': target_type,
            },
            'transformation': {
                'type': transform_type,
                'expression': expression,
                'line': line,
            },
            'cross_language': cross_language,
            'chunk_ast_path': chunk.ast_path if chunk else '',
            'file_path': file_path,
        }

    def _chunk_for_line(
        self,
        chunks: list[ChunkMetadata],
        line: int,
    ) -> ChunkMetadata | None:
        """Find the chunk that covers a given source line."""
        for chunk in chunks:
            if chunk.start_line <= line <= chunk.end_line:
                return chunk
        return chunks[0] if chunks else None

    @staticmethod
    def _extract_sql_entities(sql_text: str) -> list[tuple[str, str]]:
        """Extract table names and inferred read/write direction from SQL text."""
        normalised = sql_text.upper().strip('"')
        direction = 'WRITE' if any(keyword in normalised for keyword in ['INSERT', 'UPDATE', 'DELETE', 'MERGE']) else 'READ'
        return [
            (match.group(1).strip('`"'), direction)
            for match in _TABLE_PATTERN.finditer(sql_text)
        ] or [(sql_text[:80], direction)]

    @staticmethod
    def _split_reference(reference: str) -> tuple[str, str]:
        """Split ``table.column`` references into entity and column parts."""
        cleaned = reference.strip().strip('`"')
        if '.' not in cleaned:
            return '', cleaned
        entity, column = cleaned.rsplit('.', 1)
        return entity, column

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """Detect supported language from filename extension."""
        suffix = Path(file_path).suffix.lower()
        if suffix in _COBOL_EXTENSIONS:
            return 'COBOL'
        if suffix in _JAVA_EXTENSIONS:
            return 'Java'
        if suffix in _SQL_EXTENSIONS:
            return 'SQL'
        return 'unknown'

    @staticmethod
    def _assertion_key(assertion: dict[str, Any]) -> tuple[str, str, str, int]:
        """Build a deduplication key for golden assertions."""
        return (
            str(assertion['source'].get('entity', '')).upper(),
            str(assertion['target'].get('entity', '')).upper(),
            str(assertion['transformation'].get('type', '')).upper(),
            int(assertion['transformation'].get('line', 0) or 0),
        )
