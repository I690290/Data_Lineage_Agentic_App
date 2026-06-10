from __future__ import annotations

from statistics import mean
from typing import Any


class SystemEvaluator:
    """Aggregate file-level results into end-to-end system metrics."""

    def evaluate(
        self,
        all_file_results: list[dict[str, Any]],
        golden_cross_language: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute aggregate system metrics.

        Args:
            all_file_results: File-level evaluation outputs.
            golden_cross_language: Golden cross-language assertions.

        Returns:
            Aggregate system-level metrics.
        """
        if not all_file_results:
            return {
                "total_files": 0,
                "end_to_end_lineage_completeness": 0.0,
                "cross_language_link_accuracy": 0.0,
                "openlineage_schema_compliance": 0.0,
                "processing_latency_ms": self._latency_stats([]),
            }

        precisions = [float(result.get("precision", 0.0) or 0.0) for result in all_file_results]
        recalls = [float(result.get("recall", 0.0) or 0.0) for result in all_file_results]
        f1_scores = [float(result.get("f1_score", 0.0) or 0.0) for result in all_file_results]
        hallucination_rates = [float(result.get("hallucination_rate", 0.0) or 0.0) for result in all_file_results]
        latencies = self._collect_latencies(all_file_results)
        extracted_cross_language = self._collect_cross_language(all_file_results)
        cross_language_accuracy = self._cross_language_accuracy(extracted_cross_language, golden_cross_language)
        compliance_score, compliant_events, total_events = self._openlineage_compliance(all_file_results)
        files_passed = sum(1 for result in all_file_results if result.get("passed", False))

        return {
            "total_files": len(all_file_results),
            "files_passed": files_passed,
            "files_failed": len(all_file_results) - files_passed,
            "aggregate_precision": round(mean(precisions), 4),
            "aggregate_recall": round(mean(recalls), 4),
            "aggregate_f1": round(mean(f1_scores), 4),
            "aggregate_hallucination_rate": round(mean(hallucination_rates), 4),
            "end_to_end_lineage_completeness": round(mean(recalls), 4),
            "cross_language_link_accuracy": round(cross_language_accuracy, 4),
            "cross_language_links_expected": len(golden_cross_language),
            "cross_language_links_found": len(extracted_cross_language),
            "openlineage_schema_compliance": round(compliance_score, 4),
            "openlineage_compliant_events": compliant_events,
            "openlineage_events_total": total_events,
            "processing_latency_ms": self._latency_stats(latencies),
        }

    def _collect_cross_language(self, file_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract predicted cross-language flows from file results."""
        collected: list[dict[str, Any]] = []
        candidate_keys = (
            "cross_language_assertions",
            "cross_language_results",
            "predicted_cross_language",
            "extracted_cross_language",
        )
        for result in file_results:
            for key in candidate_keys:
                value = result.get(key)
                if isinstance(value, list):
                    collected.extend(item for item in value if isinstance(item, dict))
        return collected

    def _cross_language_accuracy(
        self,
        predicted: list[dict[str, Any]],
        golden: list[dict[str, Any]],
    ) -> float:
        """Compute accuracy of predicted cross-language links."""
        if not golden:
            return 1.0 if not predicted else 0.0
        used: set[int] = set()
        matches = 0
        for predicted_assertion in predicted:
            predicted_key = self._assertion_key(predicted_assertion)
            for index, golden_assertion in enumerate(golden):
                if index in used:
                    continue
                if predicted_key == self._assertion_key(golden_assertion):
                    used.add(index)
                    matches += 1
                    break
        return matches / len(golden)

    def _openlineage_compliance(self, file_results: list[dict[str, Any]]) -> tuple[float, int, int]:
        """Measure how many supplied OpenLineage events satisfy a minimal schema."""
        total_events = 0
        compliant_events = 0
        for result in file_results:
            events = result.get("openlineage_events", [])
            if not isinstance(events, list):
                continue
            for event in events:
                total_events += 1
                if self._is_openlineage_event_valid(event):
                    compliant_events += 1
        if total_events == 0:
            return 1.0, 0, 0
        return compliant_events / total_events, compliant_events, total_events

    def _collect_latencies(self, file_results: list[dict[str, Any]]) -> list[float]:
        """Collect per-file latency measurements in milliseconds."""
        latencies: list[float] = []
        for result in file_results:
            for key in ("processing_latency_ms", "latency_ms", "elapsed_ms"):
                value = result.get(key)
                if value is None:
                    continue
                try:
                    latencies.append(float(value))
                    break
                except (TypeError, ValueError):
                    continue
        return latencies

    def _latency_stats(self, latencies: list[float]) -> dict[str, float]:
        """Calculate summary latency statistics."""
        if not latencies:
            return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0}
        ordered = sorted(latencies)
        return {
            "count": float(len(ordered)),
            "min": round(ordered[0], 4),
            "max": round(ordered[-1], 4),
            "avg": round(mean(ordered), 4),
            "p50": round(self._percentile(ordered, 0.50), 4),
            "p95": round(self._percentile(ordered, 0.95), 4),
        }

    def _percentile(self, ordered: list[float], quantile: float) -> float:
        """Compute an interpolated percentile for ordered values."""
        if not ordered:
            return 0.0
        if len(ordered) == 1:
            return ordered[0]
        position = (len(ordered) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    def _is_openlineage_event_valid(self, event: dict[str, Any]) -> bool:
        """Validate a minimal OpenLineage event structure."""
        if not isinstance(event, dict):
            return False
        required_scalar_paths = [
            ("eventType",),
            ("eventTime",),
            ("job", "name"),
            ("job", "namespace"),
        ]
        for path in required_scalar_paths:
            cursor: Any = event
            for key in path:
                if not isinstance(cursor, dict) or key not in cursor:
                    return False
                cursor = cursor[key]
            if cursor in (None, ""):
                return False
        return isinstance(event.get("inputs", []), list) and isinstance(event.get("outputs", []), list)

    @staticmethod
    def _assertion_key(assertion: dict[str, Any]) -> tuple[str, str, str]:
        """Create a canonical key for a lineage assertion."""
        source = str(assertion.get("source", {}).get("entity", "")).strip().upper()
        target = str(assertion.get("target", {}).get("entity", "")).strip().upper()
        transformation = str(assertion.get("transformation", {}).get("type", "")).strip().upper()
        return source, target, transformation
