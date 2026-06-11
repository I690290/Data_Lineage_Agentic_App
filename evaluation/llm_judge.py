"""LLM-as-judge for semantic equivalence of unmatched lineage assertion pairs."""
from __future__ import annotations

import json
from typing import Any


_JUDGE_PROMPT_TEMPLATE = """\
You are a data lineage expert evaluating whether two lineage assertion pairs refer to the same physical data entity or transformation.

EXTRACTED assertion (from the agent):
  Source entity: {ext_source}
  Target entity: {ext_target}
  Transformation type: {ext_transform}

EXPECTED assertion (from the ground truth):
  Source entity: {gt_source}
  Target entity: {gt_target}
  Transformation type: {gt_transform}

Context: These come from a legacy COBOL/JCL/Oracle SQL ETL pipeline.
Entity names may differ due to:
  - DD name vs physical DSN vs logical alias (e.g. "BHSCOEXT" vs "CUST.BHSCORE.EXTRACT")
  - Schema prefix elision (e.g. "CRISK.CUST_ACCOUNT_MASTER" vs "CUST_ACCOUNT_MASTER")
  - Abbreviation (e.g. "TXN" vs "TRANSACTION", "STG" vs "STAGING")
  - Case difference

Answer with ONLY a JSON object on a single line:
{{"equivalent": true/false, "confidence": 0.0-1.0, "reason": "one sentence"}}
"""


class LLMJudge:
    """Use a Bedrock LLM to decide semantic equivalence for unmatched assertion pairs.

    Only invoked on the *unmatched* pairs from Level 2 FileEvaluator to avoid
    false-negatives from naming mismatches.  Adds a ``judge_verdict`` field to
    each pair and adjusts true-positive counts accordingly.

    Args:
        model_id: Bedrock model ID.  Defaults to ``amazon.nova-pro-v1:0``.
        region: AWS region.  Defaults to ``us-east-1``.
        threshold: Confidence threshold above which the judge verdict is accepted.
    """

    def __init__(
        self,
        model_id: str = "amazon.nova-pro-v1:0",
        region: str = "us-east-1",
        threshold: float = 0.75,
    ) -> None:
        self._model_id = model_id
        self._region = region
        self._threshold = threshold
        self._client: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def judge_unmatched_pairs(
        self,
        extracted: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
        matched_extracted_indices: set[int],
        matched_gt_indices: set[int],
    ) -> dict[str, Any]:
        """Run the LLM judge on unmatched extracted vs unmatched ground-truth pairs.

        Args:
            extracted: Full list of extracted assertions.
            ground_truth: Full list of golden assertions.
            matched_extracted_indices: Extracted indices already matched by string match.
            matched_gt_indices: Ground-truth indices already matched by string match.

        Returns:
            Dict with ``additional_true_positives``, ``verdicts``, and
            ``adjusted_true_positives`` total.
        """
        unmatched_ext = [
            (i, a) for i, a in enumerate(extracted) if i not in matched_extracted_indices
        ]
        unmatched_gt = [
            (j, a) for j, a in enumerate(ground_truth) if j not in matched_gt_indices
        ]

        if not unmatched_ext or not unmatched_gt:
            return {"additional_true_positives": 0, "verdicts": [], "skipped": True}

        verdicts: list[dict[str, Any]] = []
        used_gt: set[int] = set()
        extra_tp = 0

        for ext_idx, ext_assertion in unmatched_ext:
            best_verdict = None
            best_conf = 0.0
            best_gt_idx = None

            for gt_idx, gt_assertion in unmatched_gt:
                if gt_idx in used_gt:
                    continue
                verdict = self._invoke_judge(ext_assertion, gt_assertion)
                if verdict.get("equivalent") and verdict.get("confidence", 0.0) >= self._threshold:
                    if verdict["confidence"] > best_conf:
                        best_conf = verdict["confidence"]
                        best_verdict = verdict
                        best_gt_idx = gt_idx

            if best_verdict and best_gt_idx is not None:
                used_gt.add(best_gt_idx)
                extra_tp += 1
                verdicts.append({
                    "extracted_index": ext_idx,
                    "gt_index": best_gt_idx,
                    "verdict": best_verdict,
                    "extracted": _assertion_summary(extracted[ext_idx]),
                    "ground_truth": _assertion_summary(ground_truth[best_gt_idx]),
                })

        return {
            "additional_true_positives": extra_tp,
            "verdicts": verdicts,
            "skipped": False,
        }

    def is_available(self) -> bool:
        """Return True if the Bedrock client can be initialised."""
        try:
            self._get_client()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # LLM invocation
    # ------------------------------------------------------------------

    def _invoke_judge(
        self,
        extracted: dict[str, Any],
        ground_truth: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = _JUDGE_PROMPT_TEMPLATE.format(
            ext_source=extracted.get("source", {}).get("entity", ""),
            ext_target=extracted.get("target", {}).get("entity", ""),
            ext_transform=extracted.get("transformation", {}).get("type", ""),
            gt_source=ground_truth.get("source", {}).get("entity", ""),
            gt_target=ground_truth.get("target", {}).get("entity", ""),
            gt_transform=ground_truth.get("transformation", {}).get("type", ""),
        )
        try:
            client = self._get_client()
            body = {
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                "max_tokens": 200,
                "temperature": 0.0,
            }
            response = client.invoke_model(
                modelId=self._model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            raw = json.loads(response["body"].read())
            text = raw.get("content", [{}])[0].get("text", "")
            return json.loads(text.strip())
        except Exception as exc:
            return {"equivalent": False, "confidence": 0.0, "reason": f"judge_error: {exc}"}

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client


def _assertion_summary(assertion: dict[str, Any]) -> str:
    src = assertion.get("source", {}).get("entity", "?")
    tgt = assertion.get("target", {}).get("entity", "?")
    t_type = assertion.get("transformation", {}).get("type", "?")
    return f"{src} --[{t_type}]--> {tgt}"
