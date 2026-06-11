"""Three-level evaluation framework for lineage extraction quality."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.expected_lineage_evaluator import ExpectedLineageEvaluator
from evaluation.golden_dataset_generator import GoldenDatasetGenerator
from evaluation.level1_assertion import AssertionEvaluator
from evaluation.level2_file import FileEvaluator
from evaluation.level3_system import SystemEvaluator
from evaluation.llm_judge import LLMJudge
from evaluation.path_evaluator import PathEvaluator
from parsers.orchestrator import ParserOrchestrator


class EvaluationRunner:
    """Orchestrate the full evaluation suite and emit JSON reports.

    Runs five complementary checks in sequence:
    1. Level 1 (AssertionEvaluator) — per-assertion AST validation.
    2. Level 2 (FileEvaluator)      — per-file precision / recall / F1.
    3. Level 3 (SystemEvaluator)    — aggregate system metrics.
    4. Oracle  (ExpectedLineageEvaluator) — node/edge checklist against known ground truth.
    5. Path    (PathEvaluator)      — end-to-end chain completeness.
    6. Judge   (LLMJudge)           — semantic equivalence for unmatched pairs (optional).

    All evaluation spans are exported to OTel / Jaeger when tracing is available.
    """

    def __init__(
        self,
        golden_generator: GoldenDatasetGenerator | None = None,
        orchestrator: ParserOrchestrator | None = None,
        oracle_path: str | Path | None = None,
        enable_llm_judge: bool = False,
    ) -> None:
        self._golden_gen = golden_generator or GoldenDatasetGenerator()
        self._orchestrator = orchestrator or ParserOrchestrator()
        self._level1 = AssertionEvaluator()
        self._level2 = FileEvaluator()
        self._level3 = SystemEvaluator()
        self._oracle_eval = ExpectedLineageEvaluator(oracle_path)
        self._path_eval = PathEvaluator(oracle_path)
        self._judge = LLMJudge() if enable_llm_judge else None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_full_evaluation(
        self,
        extracted_dir: str,
        golden_dir: str,
    ) -> dict[str, Any]:
        """Run all evaluation levels from saved JSON assets on disk.

        Args:
            extracted_dir: Directory containing extracted lineage JSON files
                (``*_lineage.json`` from the pipeline).
            golden_dir: Directory containing ``*.golden.json`` files.

        Returns:
            Complete evaluation report with all five evaluation layers.
        """
        tracer = self._get_tracer()
        start = time.monotonic()

        with _span(tracer, "evaluation.full_run") as span:
            _set(span, "evaluation.extracted_dir", extracted_dir)
            _set(span, "evaluation.golden_dir", golden_dir)

            # ── Load golden datasets ──────────────────────────────────
            golden_map, golden_cross_language = self._load_golden(golden_dir)

            # ── Load extracted lineage ────────────────────────────────
            extracted_map = self._load_extracted(extracted_dir)

            # ── Level 2: per-file evaluation ─────────────────────────
            file_results = self._run_file_evaluation(extracted_map, golden_map, tracer)

            # ── Level 3: system aggregate ────────────────────────────
            system_result = self._run_system_evaluation(file_results, golden_cross_language, tracer)

            # ── Oracle: expected lineage checklist ───────────────────
            all_nodes, all_edges = self._collect_nodes_edges(extracted_map)
            oracle_result = self._run_oracle_evaluation(all_nodes, all_edges, tracer)

            # ── Path: end-to-end chain completeness ──────────────────
            path_result = self._run_path_evaluation(all_nodes, all_edges, tracer)

            # ── Compile report ───────────────────────────────────────
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            report = {
                "evaluation_timestamp": datetime.now(UTC).isoformat(),
                "elapsed_ms": elapsed_ms,
                "summary": system_result,
                "oracle_evaluation": oracle_result,
                "path_evaluation": path_result,
                "file_results": file_results,
            }

            _set(span, "evaluation.files_evaluated", len(file_results))
            _set(span, "evaluation.oracle_passed", oracle_result.get("overall_passed", False))
            _set(span, "evaluation.path_passed", path_result.get("overall_passed", False))

        self._save_report(report)
        self._print_summary(report)
        return report

    def run_oracle_only(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
        extracted_column_lineage: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run only the oracle + path checks on live extracted data (no disk I/O).

        Useful for inline validation inside the pipeline after each file batch.

        Args:
            extracted_nodes: Node dicts from pipeline state.
            extracted_edges: Edge dicts from pipeline state.
            extracted_column_lineage: Optional column mapping list.

        Returns:
            Oracle and path evaluation results.
        """
        tracer = self._get_tracer()
        oracle_result = self._run_oracle_evaluation(extracted_nodes, extracted_edges, tracer, extracted_column_lineage)
        path_result = self._run_path_evaluation(extracted_nodes, extracted_edges, tracer)
        return {
            "oracle_evaluation": oracle_result,
            "path_evaluation": path_result,
            "overall_passed": oracle_result.get("overall_passed", False) and path_result.get("overall_passed", False),
        }

    # ------------------------------------------------------------------
    # Per-level runners (each wrapped in its own OTel span)
    # ------------------------------------------------------------------

    def _run_file_evaluation(
        self,
        extracted_map: dict[str, list[dict[str, Any]]],
        golden_map: dict[str, dict[str, Any]],
        tracer: Any,
    ) -> list[dict[str, Any]]:
        file_results: list[dict[str, Any]] = []
        for stem, golden in golden_map.items():
            extracted = extracted_map.get(stem, [])
            with _span(tracer, "evaluation.level2.file") as span:
                _set(span, "evaluation.file_path", golden.get("file_path", stem))
                t0 = time.monotonic()
                result = self._level2.evaluate(extracted, golden)
                result["openlineage_events"] = self._normalise_events(extracted)

                # LLM judge for unmatched pairs if enabled
                if self._judge and self._judge.is_available():
                    matched_ext = {p["extracted_index"] for p in result.get("matched_pairs", [])}
                    matched_gt = {p["ground_truth_index"] for p in result.get("matched_pairs", [])}
                    ground_truth = list(golden.get("ground_truth_assertions", []))
                    judge_result = self._judge.judge_unmatched_pairs(extracted, ground_truth, matched_ext, matched_gt)
                    result["llm_judge"] = judge_result
                    if not judge_result.get("skipped"):
                        extra_tp = judge_result.get("additional_true_positives", 0)
                        # Adjust metrics with judge-confirmed true positives
                        adjusted_tp = result["true_positives"] + extra_tp
                        ec = result["extracted_count"]
                        gc = result["ground_truth_count"]
                        adj_precision = adjusted_tp / ec if ec else 0.0
                        adj_recall = adjusted_tp / gc if gc else 0.0
                        result["adjusted_precision"] = round(adj_precision, 4)
                        result["adjusted_recall"] = round(adj_recall, 4)
                        result["adjusted_f1"] = round(
                            2 * adj_precision * adj_recall / (adj_precision + adj_recall)
                            if adj_precision + adj_recall else 0.0, 4
                        )

                result["processing_latency_ms"] = round((time.monotonic() - t0) * 1000, 2)
                _set(span, "evaluation.precision", result.get("precision", 0))
                _set(span, "evaluation.recall", result.get("recall", 0))
                _set(span, "evaluation.f1", result.get("f1_score", 0))
                _set(span, "evaluation.hallucination_rate", result.get("hallucination_rate", 0))
                _set(span, "evaluation.passed", result.get("passed", False))

            file_results.append(result)
        return file_results

    def _run_system_evaluation(
        self,
        file_results: list[dict[str, Any]],
        golden_cross_language: list[dict[str, Any]],
        tracer: Any,
    ) -> dict[str, Any]:
        with _span(tracer, "evaluation.level3.system") as span:
            result = self._level3.evaluate(file_results, golden_cross_language)
            _set(span, "evaluation.aggregate_f1", result.get("aggregate_f1", 0))
            _set(span, "evaluation.cross_language_accuracy", result.get("cross_language_link_accuracy", 0))
            _set(span, "evaluation.openlineage_compliance", result.get("openlineage_schema_compliance", 0))
        return result

    def _run_oracle_evaluation(
        self,
        all_nodes: list[dict[str, Any]],
        all_edges: list[dict[str, Any]],
        tracer: Any,
        col_lineage: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with _span(tracer, "evaluation.oracle.checklist") as span:
            result = self._oracle_eval.evaluate(all_nodes, all_edges, col_lineage)
            _set(span, "evaluation.oracle.checks_passed", result.get("checks_passed", 0))
            _set(span, "evaluation.oracle.checks_failed", result.get("checks_failed", 0))
            _set(span, "evaluation.oracle.pass_rate", result.get("pass_rate", 0))
            _set(span, "evaluation.oracle.overall_passed", result.get("overall_passed", False))
            # Emit one child span per failed check for fine-grained tracing
            for item in result.get("failed_checks", []):
                with _span(tracer, f"evaluation.oracle.check.{item['check']}") as child:
                    _set(child, "evaluation.check.expected", str(item.get("expected", "")))
                    _set(child, "evaluation.check.found", str(item.get("found", "")))
                    _set(child, "evaluation.check.passed", False)
        return result

    def _run_path_evaluation(
        self,
        all_nodes: list[dict[str, Any]],
        all_edges: list[dict[str, Any]],
        tracer: Any,
    ) -> dict[str, Any]:
        with _span(tracer, "evaluation.path.completeness") as span:
            result = self._path_eval.evaluate(all_nodes, all_edges)
            _set(span, "evaluation.path.total", result.get("total_paths", 0))
            _set(span, "evaluation.path.passed", result.get("paths_passed", 0))
            _set(span, "evaluation.path.failed", result.get("paths_failed", 0))
            _set(span, "evaluation.path.completeness", result.get("path_completeness", 0))
        return result

    # ------------------------------------------------------------------
    # Data loading helpers
    # ------------------------------------------------------------------

    def _load_golden(self, golden_dir: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        golden_map: dict[str, dict[str, Any]] = {}
        golden_cross_language: list[dict[str, Any]] = []
        for golden_file in Path(golden_dir).glob("*.golden.json"):
            try:
                golden = json.loads(golden_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[eval] Skipping corrupt golden file {golden_file}: {exc}")
                continue
            fp = golden.get("file_path", golden_file.name)
            golden_map[Path(fp).stem] = golden
            golden_cross_language.extend(golden.get("ground_truth_cross_language", []))
        return golden_map, golden_cross_language

    def _load_extracted(self, extracted_dir: str) -> dict[str, list[dict[str, Any]]]:
        extracted_map: dict[str, list[dict[str, Any]]] = {}
        for extracted_file in Path(extracted_dir).glob("*_lineage.json"):
            stem = extracted_file.stem.replace("_lineage", "")
            try:
                events = json.loads(extracted_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            extracted_map[stem] = self._flatten_events(events)
        return extracted_map

    def _collect_nodes_edges(
        self, extracted_map: dict[str, list[dict[str, Any]]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Flatten all extracted assertions into deduplicated node/edge lists."""
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str]] = set()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for assertions in extracted_map.values():
            for a in assertions:
                src = a.get("source", {}).get("entity", "")
                tgt = a.get("target", {}).get("entity", "")
                if src and src not in seen_nodes:
                    seen_nodes.add(src)
                    nodes.append({"name": src, "id": src})
                if tgt and tgt not in seen_nodes:
                    seen_nodes.add(tgt)
                    nodes.append({"name": tgt, "id": tgt})
                edge_key = (src, tgt)
                if src and tgt and edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append({"source": src, "target": tgt})
        return nodes, edges

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _flatten_events(self, events: Any) -> list[dict[str, Any]]:
        """Convert OpenLineage-style events to assertion-like structures."""
        if not isinstance(events, list):
            return []
        assertions: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            for input_dataset in event.get("inputs", []):
                for output_dataset in event.get("outputs", []):
                    assertions.append(
                        {
                            "source": {
                                "entity": input_dataset.get("name", ""),
                                "column": "",
                                "type": "table",
                            },
                            "target": {
                                "entity": output_dataset.get("name", ""),
                                "column": "",
                                "type": "table",
                            },
                            "transformation": {
                                "type": event.get("eventType", "EXTRACTED"),
                                "expression": event.get("job", {}).get("name", ""),
                                "line": 0,
                            },
                            "confidence": output_dataset.get("confidence", 0.5),
                        }
                    )
        return assertions

    def _normalise_events(self, assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Wrap assertion-like records in a minimal OpenLineage event shape."""
        return [
            {
                "eventType": a.get("transformation", {}).get("type", "COMPLETE"),
                "eventTime": datetime.now(UTC).isoformat(),
                "job": {"namespace": "evaluation", "name": "flattened_assertion"},
                "inputs": [{"name": a.get("source", {}).get("entity", "")}],
                "outputs": [{"name": a.get("target", {}).get("entity", "")}],
            }
            for a in assertions
        ]

    # ------------------------------------------------------------------
    # Report I/O
    # ------------------------------------------------------------------

    def _save_report(self, report: dict[str, Any]) -> None:
        reports_dir = Path("evaluation/reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"eval_{timestamp}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[eval] Report saved to {report_path}")

    @staticmethod
    def _print_summary(report: dict[str, Any]) -> None:
        summary = report["summary"]
        oracle = report.get("oracle_evaluation", {})
        path = report.get("path_evaluation", {})
        print("\n" + "=" * 70)
        print("EVALUATION SUMMARY")
        print("=" * 70)
        print("  >> Level 3 — System Metrics:")
        for key, value in summary.items():
            print(f"     {key:<40} {value}")
        print()
        print("  >> Oracle Checklist (expected_lineage.json):")
        print(f"     {'checks_passed':<40} {oracle.get('checks_passed', '?')}/{oracle.get('total_checks', '?')}")
        print(f"     {'pass_rate':<40} {oracle.get('pass_rate', 0):.1%}")
        print(f"     {'overall_passed':<40} {oracle.get('overall_passed', False)}")
        if oracle.get("failed_checks"):
            print("     FAILED CHECKS:")
            for fc in oracle["failed_checks"]:
                print(f"       - {fc['check']}: expected={fc['expected']!r} found={fc['found']!r}")
        print()
        print("  >> Path Completeness:")
        print(f"     {'paths_passed':<40} {path.get('paths_passed', '?')}/{path.get('total_paths', '?')}")
        print(f"     {'path_completeness':<40} {path.get('path_completeness', 0):.1%}")
        if path.get("reflexion_hints"):
            print("     BROKEN PATHS:")
            for hint in path["reflexion_hints"]:
                print(f"       - {hint[:120]}")
        print("=" * 70 + "\n")

    @staticmethod
    def _get_tracer() -> Any:
        try:
            from observability.tracing import get_tracer
            return get_tracer()
        except Exception:
            return _NoopTracer()


# ---------------------------------------------------------------------------
# OTel span helpers
# ---------------------------------------------------------------------------

class _NoopSpan:
    def __enter__(self) -> "_NoopSpan":
        return self
    def __exit__(self, *args: Any) -> None:
        pass
    def set_attribute(self, *args: Any) -> None:
        pass


class _NoopTracer:
    def start_as_current_span(self, name: str) -> _NoopSpan:
        return _NoopSpan()


def _span(tracer: Any, name: str) -> Any:
    try:
        return tracer.start_as_current_span(name)
    except Exception:
        return _NoopSpan()


def _set(span: Any, key: str, value: Any) -> None:
    try:
        span.set_attribute(key, value)
    except Exception:
        pass


__all__ = [
    "GoldenDatasetGenerator",
    "AssertionEvaluator",
    "FileEvaluator",
    "SystemEvaluator",
    "EvaluationRunner",
    "ExpectedLineageEvaluator",
    "PathEvaluator",
    "LLMJudge",
]
