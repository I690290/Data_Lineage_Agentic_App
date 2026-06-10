"""Reflexion retry mechanism with episodic memory accumulation."""
from __future__ import annotations

from typing import Any


class ReflexionRetry:
    """Implement the Reflexion cognitive pattern for lineage extraction.

    When verification fails, failed assertion context is appended to
    ``episodic_memory`` in the state, giving the next agent invocation
    corrective information to produce a better assertion.

    Episodic memory entries follow this format::

        "Attempt 1 FAILED: Asserted MOVE ACCT-NUM TO WS-ACCT at line 142,
        but AST query found no MOVE statement at that location.
        Nearest MOVE to WS-ACCT is at line 158: MOVE ACCT-NUMBER TO WS-ACCT."

    Args:
        max_retries: Maximum number of retry attempts before escalating to
            human review. Defaults to 3.
    """

    MAX_RETRIES: int = 3

    def __init__(self, max_retries: int = 3) -> None:
        self.MAX_RETRIES = max_retries

    def update_state(
        self,
        state: dict[str, Any],
        verification_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Update agent state after a verification failure.

        Appends failure context to ``episodic_memory``, increments
        ``retry_count``, and moves assertions that exhausted retries to
        ``needs_human_review``.

        Args:
            state: Current LangGraph state dict.
            verification_results: Results from ``VerificationGate.verify()``.

        Returns:
            Updated state dict with ``retry_count``, ``episodic_memory``,
            and ``needs_human_review`` populated.
        """
        retry_count = state.get("retry_count", 0)
        episodic_memory: list[str] = list(state.get("episodic_memory", []))
        needs_human_review: list[dict[str, Any]] = list(state.get("needs_human_review", []))
        extracted_assertions: list[dict[str, Any]] = list(state.get("extracted_assertions", []))

        failed_results = [r for r in verification_results if not r.get("passed", True)]

        if retry_count >= self.MAX_RETRIES:
            # Escalate all remaining failures to human review
            assertion_ids = {r["assertion_id"] for r in failed_results}
            for assertion in extracted_assertions:
                if assertion.get("id") in assertion_ids:
                    review_entry = {
                        **assertion,
                        "review_reason": "exceeded_max_retries",
                        "retry_count": retry_count,
                        "failure_history": episodic_memory,
                        "confidence": min(float(assertion.get("confidence", 0.5)), 0.4),
                    }
                    needs_human_review.append(review_entry)
            return {
                **state,
                "needs_human_review": needs_human_review,
                "retry_count": retry_count,
            }

        # Build episodic memory entries for each failure
        for result in failed_results:
            assertion_id = result.get("assertion_id", "unknown")
            error_msg = result.get("error_msg", "verification failed")
            evidence = result.get("evidence", "")
            failed_checks = [c["name"] for c in result.get("checks", []) if not c.get("passed", True)]

            memory_entry = (
                f"Attempt {retry_count + 1} FAILED for assertion {assertion_id}: "
                f"{error_msg}. "
                f"Failed checks: {failed_checks}. "
                f"Evidence found: {evidence or 'none'}. "
                f"Please re-examine the source code more carefully and correct the assertion."
            )
            episodic_memory.append(memory_entry)

        return {
            **state,
            "retry_count": retry_count + 1,
            "episodic_memory": episodic_memory,
            "needs_human_review": needs_human_review,
        }

    def build_retry_context(self, episodic_memory: list[str]) -> str:
        """Build a formatted retry context string to prepend to agent prompts.

        Args:
            episodic_memory: List of failure context strings accumulated
                across retry attempts.

        Returns:
            Formatted multi-line string describing past failures for the agent.
        """
        if not episodic_memory:
            return ""
        lines = [
            "PREVIOUS ATTEMPTS FAILED — CORRECTION CONTEXT:",
            "=" * 50,
        ]
        for i, entry in enumerate(episodic_memory, 1):
            lines.append(f"[Failure {i}] {entry}")
        lines.extend([
            "=" * 50,
            "Using the above context, correct your assertions before responding.",
            "Focus on exact line numbers and verified entity names.",
        ])
        return "\n".join(lines)

    @staticmethod
    def partition_assertions(
        assertions: list[dict[str, Any]],
        verification_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split assertions into (passed, failed) lists.

        Args:
            assertions: Full list of extracted assertions.
            verification_results: Corresponding verification result dicts.

        Returns:
            Tuple of ``(passed_assertions, failed_assertions)``.
        """
        passed_ids = {r["assertion_id"] for r in verification_results if r.get("passed", True)}
        passed = [a for a in assertions if a.get("id") in passed_ids]
        failed = [a for a in assertions if a.get("id") not in passed_ids]
        return passed, failed
