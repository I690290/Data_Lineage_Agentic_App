from __future__ import annotations

from typing import Any


class FileEvaluator:
    """Evaluate extracted assertions for a single file against ground truth."""

    def evaluate(self, extracted: list[dict[str, Any]], golden: dict[str, Any]) -> dict[str, Any]:
        """Compute file-level precision, recall, F1, and hallucination rate.

        Args:
            extracted: Extracted lineage assertions.
            golden: Golden dataset for the file.

        Returns:
            File-level metrics and pass/fail state.
        """
        ground_truth = list(golden.get("ground_truth_assertions", []))
        matches = self._match_assertions(extracted, ground_truth)
        true_positives = len(matches)
        extracted_count = len(extracted)
        ground_truth_count = len(ground_truth)

        precision = 1.0 if extracted_count == 0 and ground_truth_count == 0 else true_positives / extracted_count if extracted_count else 0.0
        recall = 1.0 if ground_truth_count == 0 and extracted_count == 0 else true_positives / ground_truth_count if ground_truth_count else 0.0
        f1_score = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        hallucinations = self._count_hallucinations(extracted, golden)
        hallucination_rate = hallucinations / extracted_count if extracted_count else 0.0

        return {
            "file_path": golden.get("file_path", ""),
            "language": golden.get("language", ""),
            "extracted_count": extracted_count,
            "ground_truth_count": ground_truth_count,
            "true_positives": true_positives,
            "false_positives": max(0, extracted_count - true_positives),
            "false_negatives": max(0, ground_truth_count - true_positives),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "hallucination_count": hallucinations,
            "hallucination_rate": round(hallucination_rate, 4),
            "matched_pairs": matches,
            "passed": precision >= 0.90 and recall >= 0.85 and hallucination_rate < 0.05,
        }

    def _match_assertions(
        self,
        extracted: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Greedily match extracted assertions to ground truth assertions."""
        matched: list[dict[str, Any]] = []
        used_ground_truth: set[int] = set()

        for extracted_index, extracted_assertion in enumerate(extracted):
            best_match_index: int | None = None
            best_score = -1
            extracted_fingerprint = self._fingerprint(extracted_assertion)
            for ground_truth_index, golden_assertion in enumerate(ground_truth):
                if ground_truth_index in used_ground_truth:
                    continue
                golden_fingerprint = self._fingerprint(golden_assertion)
                if extracted_fingerprint == golden_fingerprint:
                    best_match_index = ground_truth_index
                    best_score = 3
                    break
                score = self._similarity_score(extracted_assertion, golden_assertion)
                if score > best_score:
                    best_score = score
                    best_match_index = ground_truth_index
            if best_match_index is not None and best_score >= 2:
                used_ground_truth.add(best_match_index)
                matched.append(
                    {
                        "extracted_index": extracted_index,
                        "ground_truth_index": best_match_index,
                        "score": best_score,
                    }
                )
        return matched

    def _count_hallucinations(self, extracted: list[dict[str, Any]], golden: dict[str, Any]) -> int:
        """Count extracted assertions that do not match any golden assertion."""
        ground_truth = list(golden.get("ground_truth_assertions", []))
        matched_pairs = self._match_assertions(extracted, ground_truth)
        return max(0, len(extracted) - len(matched_pairs))

    def _similarity_score(self, left: dict[str, Any], right: dict[str, Any]) -> int:
        """Score semantic similarity between two assertions."""
        score = 0
        if self._same_ref(left.get("source", {}), right.get("source", {})):
            score += 1
        if self._same_ref(left.get("target", {}), right.get("target", {})):
            score += 1
        if self._normalise(left.get("transformation", {}).get("type", "")) == self._normalise(
            right.get("transformation", {}).get("type", "")
        ):
            score += 1
        return score

    def _fingerprint(self, assertion: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
        """Create a canonical comparison tuple for an assertion."""
        source = assertion.get("source", {})
        target = assertion.get("target", {})
        transformation = assertion.get("transformation", {})
        return (
            self._normalise(source.get("entity", "")),
            self._normalise(source.get("column", "")),
            self._normalise(target.get("entity", "")),
            self._normalise(target.get("column", "")),
            self._normalise(source.get("type", "")),
            self._normalise(transformation.get("type", "")),
        )

    def _same_ref(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        """Compare two source/target references with tolerant matching."""
        left_entity = self._normalise(left.get("entity", ""))
        right_entity = self._normalise(right.get("entity", ""))
        left_column = self._normalise(left.get("column", ""))
        right_column = self._normalise(right.get("column", ""))
        left_type = self._normalise(left.get("type", ""))
        right_type = self._normalise(right.get("type", ""))

        entity_match = left_entity == right_entity or (left_entity and right_entity and (left_entity in right_entity or right_entity in left_entity))
        column_match = (
            left_column == right_column
            or not left_column
            or not right_column
            or (left_column in right_column or right_column in left_column)
        )
        type_match = left_type == right_type or not left_type or not right_type
        return entity_match and column_match and type_match

    @staticmethod
    def _normalise(value: Any) -> str:
        """Normalise comparable values."""
        return str(value or "").strip("'\" \t").upper()
