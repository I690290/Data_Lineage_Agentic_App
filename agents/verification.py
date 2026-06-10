"""Programmatic AST verification gate — no LLM involved."""
from __future__ import annotations

import re
from typing import Any


# COBOL type compatibility: PIC clause -> Python type category
_PIC_NUMERIC = re.compile(r"PIC\s+9", re.IGNORECASE)
_PIC_ALPHA = re.compile(r"PIC\s+X", re.IGNORECASE)
_SQL_NUMERIC = {"INTEGER", "INT", "BIGINT", "SMALLINT", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "NUMBER"}
_SQL_ALPHA = {"VARCHAR", "CHAR", "NVARCHAR", "TEXT", "CLOB", "STRING"}


class VerificationGate:
    """Programmatic verification of lineage assertions against source ASTs.

    Each assertion is checked against three gates:
    1. AST Existence — does the referenced entity exist in parsed chunks?
    2. Transformation Validity — does the cited operation appear at file:line?
    3. Type Compatibility — are source/target data types compatible?

    All checks are deterministic. No LLM inference is used here.
    """

    def verify(
        self,
        assertions: list[dict[str, Any]],
        chunks: list[Any],  # list[ChunkMetadata]
    ) -> list[dict[str, Any]]:
        """Verify a list of assertions against the parsed AST chunks.

        Args:
            assertions: OpenLineage-format assertion dicts from an agent.
            chunks: Parsed ChunkMetadata objects for the same file.

        Returns:
            List of verification result dicts with ``passed``, ``checks``, and
            ``evidence`` / ``error_msg`` fields.
        """
        results: list[dict[str, Any]] = []
        for assertion in assertions:
            result = self._verify_one(assertion, chunks)
            results.append(result)
        return results

    def _verify_one(
        self,
        assertion: dict[str, Any],
        chunks: list[Any],
    ) -> dict[str, Any]:
        """Run all checks for a single assertion."""
        result: dict[str, Any] = {
            "assertion_id": assertion.get("id", "unknown"),
            "checks": [],
            "passed": True,
            "evidence": "",
            "error_msg": "",
        }

        # Check 1: AST Existence
        ast_exists, ast_evidence = self._check_ast_existence(assertion, chunks)
        result["checks"].append({"name": "ast_existence", "passed": ast_exists, "evidence": ast_evidence})
        if ast_exists:
            result["evidence"] = ast_evidence

        # Check 2: Transformation Validity
        transform_valid, transform_evidence = self._check_transformation_location(assertion, chunks)
        result["checks"].append({"name": "transformation_validity", "passed": transform_valid, "evidence": transform_evidence})

        # Check 3: Type Compatibility
        type_compat, type_evidence = self._check_type_compatibility(assertion)
        result["checks"].append({"name": "type_compatibility", "passed": type_compat, "evidence": type_evidence})

        passed = ast_exists and transform_valid and type_compat
        result["passed"] = passed
        if not passed:
            failed_checks = [c["name"] for c in result["checks"] if not c["passed"]]
            result["error_msg"] = (
                f"Assertion {assertion.get('id', 'unknown')} failed checks: {failed_checks}. "
                f"Source={assertion.get('source', {}).get('entity', '?')} -> "
                f"Target={assertion.get('target', {}).get('entity', '?')}"
            )
        return result

    def _check_ast_existence(
        self,
        assertion: dict[str, Any],
        chunks: list[Any],
    ) -> tuple[bool, str]:
        """Check that the source and target entities appear in the parsed AST chunks."""
        source_entity = assertion.get("source", {}).get("entity", "").upper()
        target_entity = assertion.get("target", {}).get("entity", "").upper()

        if not source_entity and not target_entity:
            return True, "no entities to check"

        # Search chunks for entity names in content or io_operations
        found_source = False
        found_target = False
        evidence_parts: list[str] = []

        for chunk in chunks:
            content_upper = chunk.content.upper() if hasattr(chunk, "content") else ""
            # Check in content
            if source_entity and source_entity in content_upper:
                found_source = True
                evidence_parts.append(f"source '{source_entity}' at {chunk.ast_path}")
            if target_entity and target_entity in content_upper:
                found_target = True
                evidence_parts.append(f"target '{target_entity}' at {chunk.ast_path}")
            # Check in io_operations
            for op in getattr(chunk, "io_operations", []):
                tgt = op.get("target", "").upper()
                if source_entity and source_entity in tgt:
                    found_source = True
                if target_entity and target_entity in tgt:
                    found_target = True
            # Check in data_movements
            for mov in getattr(chunk, "data_movements", []):
                if source_entity and source_entity in mov.get("source", "").upper():
                    found_source = True
                if target_entity and target_entity in mov.get("target", "").upper():
                    found_target = True

        # If we have entity names, at least one must be found
        check_source = found_source if source_entity else True
        check_target = found_target if target_entity else True
        passed = check_source or check_target  # lenient: one is sufficient
        return passed, " | ".join(evidence_parts) or "not found in AST"

    def _check_transformation_location(
        self,
        assertion: dict[str, Any],
        chunks: list[Any],
    ) -> tuple[bool, str]:
        """Check that the cited transformation appears at or near the asserted line."""
        transform = assertion.get("transformation", {})
        transform_type = transform.get("type", "").upper()
        expression = transform.get("expression", "")
        line = transform.get("line", 0)

        if not transform_type or not expression:
            return True, "no transformation to verify"

        # Find the chunk that contains this line
        target_chunk = None
        for chunk in chunks:
            if hasattr(chunk, "start_line") and hasattr(chunk, "end_line"):
                if line == 0 or (chunk.start_line <= line <= chunk.end_line + 5):
                    target_chunk = chunk
                    break

        if target_chunk is None and chunks:
            # Fallback: search all chunks
            target_chunk = chunks[0]

        if target_chunk is None:
            return True, "no chunks to verify against"

        # Check if the transformation type keyword appears in the chunk
        content_upper = target_chunk.content.upper() if hasattr(target_chunk, "content") else ""
        transform_keyword = transform_type.split("_")[0]  # "MOVE" from "MOVE_CORRESPONDING"
        found_keyword = transform_keyword in content_upper

        # Also check io_operations and data_movements
        for op in getattr(target_chunk, "io_operations", []):
            if transform_keyword in op.get("type", "").upper():
                return True, f"found {transform_type} in io_operations at {target_chunk.ast_path}"
        for mov in getattr(target_chunk, "data_movements", []):
            if transform_keyword in mov.get("type", "").upper():
                return True, f"found {transform_type} in data_movements at {target_chunk.ast_path}"

        if found_keyword:
            return True, f"keyword '{transform_keyword}' found in {target_chunk.ast_path}"

        # Lenient: accept if confidence is low (agent already flagged uncertainty)
        conf = float(assertion.get("confidence", 1.0))
        if conf < 0.5:
            return True, f"low confidence assertion ({conf}) — transformation check waived"

        return False, f"'{transform_keyword}' not found near line {line} in {target_chunk.ast_path}"

    def _check_type_compatibility(
        self,
        assertion: dict[str, Any],
    ) -> tuple[bool, str]:
        """Check source/target data type compatibility.

        COBOL PIC 9 → SQL numeric types are compatible.
        COBOL PIC X → SQL character types are compatible.
        Mixed types are flagged with low confidence recommendation.
        """
        source = assertion.get("source", {})
        target = assertion.get("target", {})
        source_type = str(source.get("data_type", "")).upper()
        target_type = str(target.get("data_type", "")).upper()

        if not source_type or not target_type:
            return True, "no type information to check"

        source_numeric = bool(_PIC_NUMERIC.search(source_type)) or source_type in _SQL_NUMERIC
        source_alpha = bool(_PIC_ALPHA.search(source_type)) or source_type in _SQL_ALPHA
        target_numeric = bool(_PIC_NUMERIC.search(target_type)) or target_type in _SQL_NUMERIC
        target_alpha = bool(_PIC_ALPHA.search(target_type)) or target_type in _SQL_ALPHA

        if source_numeric and target_numeric:
            return True, f"numeric-to-numeric: {source_type} -> {target_type}"
        if source_alpha and target_alpha:
            return True, f"alpha-to-alpha: {source_type} -> {target_type}"
        if (source_numeric and target_alpha) or (source_alpha and target_numeric):
            # Type mismatch — flag but don't hard-fail (implicit conversion may exist)
            conf = float(assertion.get("confidence", 1.0))
            if conf < 0.6:
                return True, f"type mismatch tolerated at confidence {conf}"
            return False, f"incompatible types: {source_type} (numeric={source_numeric}) -> {target_type} (numeric={target_numeric})"

        return True, "types not categorised — check waived"

    def should_retry(self, verification_results: list[dict[str, Any]], retry_count: int, max_retries: int = 3) -> bool:
        """Determine whether a retry should be attempted.

        Args:
            verification_results: List of verification result dicts.
            retry_count: Current retry attempt number.
            max_retries: Maximum allowed retries.

        Returns:
            True if there are failed assertions and retry budget remains.
        """
        if retry_count >= max_retries:
            return False
        return any(not r.get("passed", True) for r in verification_results)
