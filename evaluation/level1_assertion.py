from __future__ import annotations

import re
from typing import Any

from parsers.models import ChunkMetadata

_READ_TYPES = {"READ", "OPEN_INPUT", "JDBC", "EMBEDDED_SQL", "JPA_QUERY", "FILE_IO", "SQL_LINEAGE", "TABLE_REF"}
_WRITE_TYPES = {"WRITE", "OPEN_OUTPUT", "OPEN_EXTEND"}
_VALUE_FLOW_TYPES = {"MOVE", "COMPUTE", "SQL_LINEAGE"}


class AssertionEvaluator:
    """Evaluate a single extracted assertion against parsed chunk evidence."""

    def evaluate(self, assertion: dict[str, Any], chunks: list[ChunkMetadata]) -> dict[str, Any]:
        """Run all level-1 checks for a single assertion.

        Args:
            assertion: Extracted lineage assertion.
            chunks: Parsed chunks for the relevant source file.

        Returns:
            Assertion-level evaluation result.
        """
        ast_existence = self._check_ast_existence(assertion, chunks)
        transformation_validity = self._check_transformation(assertion, chunks)
        type_compatibility = self._check_types(assertion)
        assertion_id = assertion.get("assertion_id") or assertion.get("id") or self._fingerprint(assertion)
        return {
            "assertion_id": assertion_id,
            "ast_existence": ast_existence,
            "transformation_validity": transformation_validity,
            "type_compatibility": type_compatibility,
            "overall_passed": ast_existence and transformation_validity and type_compatibility,
        }

    def _check_ast_existence(self, assertion: dict[str, Any], chunks: list[ChunkMetadata]) -> bool:
        """Verify that source, target, and transformation evidence exist in parsed chunks."""
        if not chunks:
            return False
        source = assertion.get("source", {})
        target = assertion.get("target", {})
        transformation = assertion.get("transformation", {})
        line = int(transformation.get("line", 0) or 0)
        candidate_chunks = self._relevant_chunks(chunks, line)
        source_found = self._side_exists(source, candidate_chunks)
        target_found = self._side_exists(target, candidate_chunks)
        return source_found and target_found

    def _check_transformation(self, assertion: dict[str, Any], chunks: list[ChunkMetadata]) -> bool:
        """Verify transformation type and operands against chunk movement/I/O metadata."""
        transformation = assertion.get("transformation", {})
        transform_type = str(transformation.get("type", "")).upper()
        line = int(transformation.get("line", 0) or 0)
        source_entity = self._normalise(assertion.get("source", {}).get("entity", ""))
        target_entity = self._normalise(assertion.get("target", {}).get("entity", ""))
        expression = self._normalise(transformation.get("expression", ""))
        if not transform_type or not chunks:
            return False

        for chunk in self._relevant_chunks(chunks, line):
            for movement in chunk.data_movements:
                movement_type = self._normalise(movement.get("type", ""))
                movement_source = self._normalise(movement.get("source", ""))
                movement_target = self._normalise(movement.get("target", ""))
                if movement_type != transform_type:
                    continue
                if source_entity and source_entity not in movement_source:
                    continue
                if target_entity and target_entity not in movement_target:
                    continue
                return True

            for io_operation in chunk.io_operations:
                operation_type = self._normalise(io_operation.get("type", ""))
                operation_target = self._normalise(io_operation.get("target", ""))
                if transform_type == "FILE_IO" and operation_type == "FILE_IO":
                    if source_entity in operation_target or target_entity in operation_target or not operation_target:
                        return True
                if transform_type == operation_type:
                    if source_entity and source_entity in operation_target:
                        return True
                    if target_entity and target_entity in operation_target:
                        return True
                    if expression and operation_target and operation_target in expression:
                        return True
                if transform_type in _READ_TYPES and operation_type in _READ_TYPES:
                    if source_entity and source_entity in operation_target:
                        return True
                if transform_type in _WRITE_TYPES and operation_type in _WRITE_TYPES:
                    if target_entity and target_entity in operation_target:
                        return True

        return False

    def _check_types(self, assertion: dict[str, Any]) -> bool:
        """Apply lightweight semantic type compatibility rules to an assertion."""
        source_type = self._normalise(assertion.get("source", {}).get("type", "unknown"))
        target_type = self._normalise(assertion.get("target", {}).get("type", "unknown"))
        transform_type = self._normalise(assertion.get("transformation", {}).get("type", ""))
        if not transform_type:
            return False

        if transform_type in _VALUE_FLOW_TYPES:
            return source_type in {"VARIABLE", "COLUMN", "LITERAL", "UNKNOWN"} and target_type in {"VARIABLE", "COLUMN", "UNKNOWN"}
        if transform_type in _READ_TYPES:
            return source_type in {"FILE", "TABLE", "DATASET", "COLUMN", "EXTERNAL_SYSTEM", "UNKNOWN"} and target_type in {"PROGRAM", "METHOD", "VARIABLE", "UNKNOWN"}
        if transform_type in _WRITE_TYPES:
            return source_type in {"PROGRAM", "METHOD", "VARIABLE", "UNKNOWN"} and target_type in {"FILE", "TABLE", "DATASET", "COLUMN", "UNKNOWN"}
        return source_type != "" and target_type != ""

    def _relevant_chunks(self, chunks: list[ChunkMetadata], line: int) -> list[ChunkMetadata]:
        """Return chunks most likely to contain evidence for the assertion."""
        if line <= 0:
            return chunks
        matching = [chunk for chunk in chunks if chunk.start_line <= line <= chunk.end_line]
        return matching or chunks

    def _side_exists(self, side: dict[str, Any], chunks: list[ChunkMetadata]) -> bool:
        """Check whether an assertion source/target exists in chunk evidence."""
        entity = self._normalise(side.get("entity", ""))
        column = self._normalise(side.get("column", ""))
        if not entity and not column:
            return False
        for chunk in chunks:
            haystacks = [
                self._normalise(chunk.ast_path),
                self._normalise(chunk.content),
                self._normalise(chunk.file_path),
            ]
            file_stem = self._normalise(re.sub(r"\.[^.]+$", "", chunk.file_path.split("/")[-1]))
            if entity and entity == file_stem:
                return True
            if any(entity and entity in haystack for haystack in haystacks):
                return True
            if any(column and column in haystack for haystack in haystacks):
                return True
            if self._exists_in_operations(entity or column, chunk.io_operations):
                return True
            if self._exists_in_movements(entity or column, chunk.data_movements):
                return True
        return False

    def _exists_in_operations(self, needle: str, operations: list[dict[str, Any]]) -> bool:
        """Check whether a token exists in I/O operation metadata."""
        for operation in operations:
            target = self._normalise(operation.get("target", ""))
            op_type = self._normalise(operation.get("type", ""))
            if needle and (needle in target or needle == op_type):
                return True
        return False

    def _exists_in_movements(self, needle: str, movements: list[dict[str, Any]]) -> bool:
        """Check whether a token exists in data movement metadata."""
        for movement in movements:
            values = [
                self._normalise(movement.get("source", "")),
                self._normalise(movement.get("target", "")),
                self._normalise(movement.get("type", "")),
            ]
            if any(needle and needle in value for value in values):
                return True
        return False

    @staticmethod
    def _fingerprint(assertion: dict[str, Any]) -> str:
        """Build a deterministic fingerprint for the evaluated assertion."""
        source = AssertionEvaluator._normalise(assertion.get("source", {}).get("entity", ""))
        target = AssertionEvaluator._normalise(assertion.get("target", {}).get("entity", ""))
        transform = AssertionEvaluator._normalise(assertion.get("transformation", {}).get("type", ""))
        line = str(assertion.get("transformation", {}).get("line", 0) or 0)
        return f"{source}:{target}:{transform}:{line}"

    @staticmethod
    def _normalise(value: Any) -> str:
        """Normalise values for case-insensitive matching."""
        return str(value or "").strip().upper()
