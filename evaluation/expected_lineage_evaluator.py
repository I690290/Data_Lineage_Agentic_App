"""Validate extracted lineage against the handcrafted expected_lineage.json oracle."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_DEFAULT_ORACLE = Path(__file__).parent.parent / "mock_code" / "expected_lineage" / "expected_lineage.json"


class ChecklistResult:
    """Outcome of a single validation checklist item."""

    def __init__(self, check: str, expected: Any, found: Any, passed: bool, detail: str = "") -> None:
        self.check = check
        self.expected = expected
        self.found = found
        self.passed = passed
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "expected": self.expected,
            "found": self.found,
            "passed": self.passed,
            "detail": self.detail,
        }


class ExpectedLineageEvaluator:
    """Compare the agent's output against the handcrafted expected lineage oracle.

    Reads ``mock_code/expected_lineage/expected_lineage.json`` and validates:
    - Node count and named node presence
    - Edge count and directed edge presence
    - COBOL program names
    - DB2 / Oracle table names
    - XML intermediate file
    - Column-level lineage path completeness
    - Copybook references
    - JCL SORT step presence

    All checks are deterministic string/set operations — no LLM involved.
    """

    def __init__(self, oracle_path: str | Path | None = None) -> None:
        path = Path(oracle_path) if oracle_path else _DEFAULT_ORACLE
        self._oracle: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self._expected_nodes: list[dict[str, Any]] = self._oracle.get("lineage_nodes", [])
        self._expected_edges: list[dict[str, Any]] = self._oracle.get("lineage_edges", [])
        self._column_lineage: list[dict[str, Any]] = self._oracle.get("column_level_lineage", [])
        self._checklist: list[dict[str, Any]] = self._oracle.get("validation_checklist", [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
        extracted_column_lineage: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run the full expected-lineage validation suite.

        Args:
            extracted_nodes: Node dicts from pipeline output (must have ``name`` key).
            extracted_edges: Edge dicts from pipeline output (must have ``source``/``target`` keys).
            extracted_column_lineage: Optional column mapping list for column-path checks.

        Returns:
            Structured report with per-check results and summary pass/fail counts.
        """
        results: list[ChecklistResult] = []
        results.extend(self._check_node_count(extracted_nodes))
        results.extend(self._check_edge_count(extracted_edges))
        results.extend(self._check_named_programs(extracted_nodes))
        results.extend(self._check_named_tables(extracted_nodes))
        results.extend(self._check_jcl_sort_step(extracted_nodes))
        results.extend(self._check_xml_intermediate(extracted_nodes))
        results.extend(self._check_copybook_references(extracted_nodes, extracted_edges))
        if extracted_column_lineage:
            results.extend(self._check_column_paths(extracted_column_lineage))
        results.extend(self._run_checklist_items(extracted_nodes, extracted_edges))

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return {
            "oracle": self._oracle.get("flow_name", "expected_lineage"),
            "total_checks": len(results),
            "checks_passed": passed,
            "checks_failed": failed,
            "pass_rate": round(passed / len(results), 4) if results else 0.0,
            "overall_passed": failed == 0,
            "results": [r.to_dict() for r in results],
            "failed_checks": [r.to_dict() for r in results if not r.passed],
        }

    def checklist_hints_for_reflexion(self, extracted_nodes: list[dict[str, Any]], extracted_edges: list[dict[str, Any]]) -> list[str]:
        """Return reflexion-ready hint strings for every failed checklist item.

        These are inserted into ``episodic_memory`` before a retry so the
        agent knows which specific lineage elements it is missing.

        Args:
            extracted_nodes: Nodes extracted so far.
            extracted_edges: Edges extracted so far.

        Returns:
            List of natural-language hint strings describing what is missing.
        """
        report = self.evaluate(extracted_nodes, extracted_edges)
        hints: list[str] = []
        for item in report["failed_checks"]:
            hint = (
                f"MISSING LINEAGE: check '{item['check']}' failed — "
                f"expected {item['expected']!r} but found {item['found']!r}. "
                f"{item['detail']} "
                f"Re-examine the source code for this element and add the missing assertion."
            )
            hints.append(hint)
        return hints

    # ------------------------------------------------------------------
    # Individual check groups
    # ------------------------------------------------------------------

    def _check_node_count(self, extracted_nodes: list[dict[str, Any]]) -> list[ChecklistResult]:
        found = len(extracted_nodes)
        expected = len(self._expected_nodes)
        passed = found >= expected
        return [ChecklistResult(
            check="node_count",
            expected=expected,
            found=found,
            passed=passed,
            detail=f"Need at least {expected} distinct lineage nodes; found {found}.",
        )]

    def _check_edge_count(self, extracted_edges: list[dict[str, Any]]) -> list[ChecklistResult]:
        found = len(extracted_edges)
        expected = len(self._expected_edges)
        passed = found >= expected
        return [ChecklistResult(
            check="edge_count",
            expected=expected,
            found=found,
            passed=passed,
            detail=f"Need at least {expected} directed edges; found {found}.",
        )]

    def _check_named_programs(self, extracted_nodes: list[dict[str, Any]]) -> list[ChecklistResult]:
        expected_programs = [n["name"] for n in self._expected_nodes if n.get("sub_type") == "COBOLProgram"]
        results = []
        extracted_names = self._node_names(extracted_nodes)
        for prog in expected_programs:
            found = any(prog.upper() in name.upper() for name in extracted_names)
            results.append(ChecklistResult(
                check=f"cobol_program:{prog}",
                expected=prog,
                found=found,
                passed=found,
                detail=f"COBOL program '{prog}' must appear as a TransformationUnit node.",
            ))
        return results

    def _check_named_tables(self, extracted_nodes: list[dict[str, Any]]) -> list[ChecklistResult]:
        db2_tables = [n["name"] for n in self._expected_nodes if n.get("sub_type") == "DB2Table"]
        oracle_tables = [
            n["name"] for n in self._expected_nodes
            if n.get("sub_type") in ("OracleTable", "OracleExternalTable", "OracleView")
        ]
        results = []
        extracted_names = self._node_names(extracted_nodes)
        for table in db2_tables:
            found = self._fuzzy_name_match(table, extracted_names)
            results.append(ChecklistResult(
                check=f"db2_table:{table}",
                expected=table,
                found=found,
                passed=found,
                detail=f"DB2 table '{table}' must appear as a DataSource node.",
            ))
        for table in oracle_tables:
            # Extract just the object name (drop schema prefix)
            short_name = table.split(".")[-1] if "." in table else table
            found = self._fuzzy_name_match(short_name, extracted_names) or self._fuzzy_name_match(table, extracted_names)
            results.append(ChecklistResult(
                check=f"oracle_object:{short_name}",
                expected=table,
                found=found,
                passed=found,
                detail=f"Oracle object '{table}' must appear as a DataSource or Dataset node.",
            ))
        return results

    def _check_jcl_sort_step(self, extracted_nodes: list[dict[str, Any]]) -> list[ChecklistResult]:
        expected = next(
            (n for n in self._expected_nodes if n.get("sub_type") == "JCLUtility"),
            None,
        )
        if not expected:
            return []
        extracted_names = self._node_names(extracted_nodes)
        keywords = {"DFSORT", "JOINKEYS", "SORT", "STEP030"}
        found = any(
            any(kw in name.upper() for kw in keywords) for name in extracted_names
        )
        return [ChecklistResult(
            check="jcl_sort_step",
            expected=expected["name"],
            found=found,
            passed=found,
            detail="DFSORT JOINKEYS STEP030 must produce a JCLUtility TransformationUnit node.",
        )]

    def _check_xml_intermediate(self, extracted_nodes: list[dict[str, Any]]) -> list[ChecklistResult]:
        xml_node = next(
            (n for n in self._expected_nodes if n.get("sub_type") == "XMLFile"),
            None,
        )
        if not xml_node:
            return []
        extracted_names = self._node_names(extracted_nodes)
        found = any(".xml" in name.lower() or "mi4014" in name.lower() for name in extracted_names)
        return [ChecklistResult(
            check="xml_intermediate_file",
            expected=xml_node["name"],
            found=found,
            passed=found,
            detail="XML transaction extract file must appear as an intermediate Dataset node.",
        )]

    def _check_copybook_references(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
    ) -> list[ChecklistResult]:
        expected_copybooks: set[str] = set()
        for node in self._expected_nodes:
            for cb in node.get("copybooks", []):
                expected_copybooks.add(cb.upper())
        if not expected_copybooks:
            return []
        extracted_names = {n.upper() for n in self._node_names(extracted_nodes)}
        edge_texts = {
            str(e.get("source", "")).upper() + str(e.get("target", "")).upper()
            for e in extracted_edges
        }
        results = []
        for cb in sorted(expected_copybooks):
            found = cb in extracted_names or any(cb in t for t in edge_texts)
            results.append(ChecklistResult(
                check=f"copybook:{cb}",
                expected=cb,
                found=found,
                passed=found,
                detail=f"Copybook '{cb}' must be referenced in an extracted node or edge.",
            ))
        return results

    def _check_column_paths(self, extracted_col_lineage: list[dict[str, Any]]) -> list[ChecklistResult]:
        end_to_end = next(
            (g for g in self._column_lineage if "end_to_end_column_paths" in g),
            None,
        )
        if not end_to_end:
            return []
        results = []
        extracted_sources = {
            str(m.get("source", "")).upper() for m in extracted_col_lineage
        }
        extracted_targets = {
            str(m.get("target", "")).upper() for m in extracted_col_lineage
        }
        for path_spec in end_to_end.get("end_to_end_column_paths", []):
            field = path_spec.get("field", "")
            path_steps: list[str] = path_spec.get("path", [])
            if len(path_steps) < 2:
                continue
            # Check first-hop (source DB2 column) and last-hop (Oracle staging column)
            source_token = _extract_column_token(path_steps[0])
            target_token = _extract_column_token(path_steps[-1])
            source_found = any(source_token in s for s in extracted_sources)
            target_found = any(target_token in t for t in extracted_targets)
            passed = source_found and target_found
            results.append(ChecklistResult(
                check=f"column_path:{field}",
                expected=f"{path_steps[0]} → {path_steps[-1]}",
                found={"source_found": source_found, "target_found": target_found},
                passed=passed,
                detail=(
                    f"End-to-end column path for '{field}' must trace "
                    f"from '{source_token}' to '{target_token}'."
                ),
            ))
        return results

    def _run_checklist_items(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
    ) -> list[ChecklistResult]:
        """Run the machine-readable validation_checklist from the oracle JSON."""
        results = []
        extracted_names = self._node_names(extracted_nodes)
        for item in self._checklist:
            check = item.get("check", "")
            expected = item.get("expected")
            description = item.get("description", "")

            if check == "Node count":
                found = len(extracted_nodes)
                passed = found >= int(expected)
            elif check == "Edge count":
                found = len(extracted_edges)
                passed = found >= int(expected)
            elif isinstance(expected, list):
                # All names in the list must be found
                missing = [e for e in expected if not self._fuzzy_name_match(e, extracted_names)]
                found = [e for e in expected if self._fuzzy_name_match(e, extracted_names)]
                passed = len(missing) == 0
            elif isinstance(expected, str):
                found = self._fuzzy_name_match(expected, extracted_names)
                passed = bool(found)
            else:
                continue  # skip unrecognised shape

            results.append(ChecklistResult(
                check=f"checklist:{check}",
                expected=expected,
                found=found,
                passed=passed,
                detail=description,
            ))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _node_names(nodes: list[dict[str, Any]]) -> list[str]:
        return [str(n.get("name") or n.get("id") or "") for n in nodes]

    @staticmethod
    def _fuzzy_name_match(needle: str, haystack: list[str]) -> bool:
        n = needle.strip("'\" \t").upper()
        if not n:
            return False
        for name in haystack:
            h = name.strip("'\" \t").upper()
            if n in h or h in n:
                return True
        return False


def _extract_column_token(step_text: str) -> str:
    """Pull the bare column/field name from a path step description."""
    # e.g. "DB2: CRISK.CUST_ACCOUNT_MASTER.EXTERNAL_ACCOUNT_NUMBER" → "EXTERNAL_ACCOUNT_NUMBER"
    # e.g. "Oracle Staging: MI4014_TRANSACCIONES_STG.MAIN_ACCOUNT_NUMBER" → "MAIN_ACCOUNT_NUMBER"
    parts = re.split(r"[:\s]+", step_text.strip())
    last = parts[-1].strip().upper()
    if "." in last:
        last = last.rsplit(".", 1)[-1]
    return last
