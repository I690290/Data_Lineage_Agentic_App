"""Custom metrics for the lineage extraction pipeline."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class LineageMetrics:
    """In-process metrics tracker for the lineage pipeline.

    Provides counters and histograms that are logged to structured JSON
    at the end of each run. Optionally exports to Prometheus if available.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._timers: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Counters
    # ------------------------------------------------------------------

    def increment(self, name: str, value: int = 1) -> None:
        """Increment a named counter.

        Args:
            name: Metric name (e.g. ``"assertions_total"``).
            value: Amount to increment by.
        """
        self._counters[name] += value

    def assertions_produced(self, count: int = 1) -> None:
        """Record new assertions produced by an agent."""
        self.increment("assertions_total", count)

    def assertions_verified(self, count: int = 1) -> None:
        """Record assertions that passed all verification checks."""
        self.increment("assertions_verified", count)

    def assertions_failed(self, count: int = 1) -> None:
        """Record assertions that failed verification after all retries."""
        self.increment("assertions_failed", count)

    def assertions_human_review(self, count: int = 1) -> None:
        """Record assertions escalated to human review."""
        self.increment("assertions_human_review", count)

    def llm_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Record Bedrock token consumption.

        Args:
            input_tokens: Number of prompt tokens.
            output_tokens: Number of completion tokens.
        """
        self.increment("llm_tokens_input_total", input_tokens)
        self.increment("llm_tokens_output_total", output_tokens)
        self.increment("llm_tokens_total", input_tokens + output_tokens)

    # ------------------------------------------------------------------
    # Histograms
    # ------------------------------------------------------------------

    def record(self, name: str, value: float) -> None:
        """Record a single observation in a histogram.

        Args:
            name: Histogram name (e.g. ``"processing_time_seconds"``).
            value: Observed value.
        """
        self._histograms[name].append(value)

    def retry_count(self, retries: int) -> None:
        """Record the number of retries for a single file."""
        self.record("retry_count", float(retries))

    def processing_time(self, seconds: float) -> None:
        """Record per-file processing duration."""
        self.record("processing_time_seconds", seconds)

    def llm_latency(self, seconds: float) -> None:
        """Record per-invocation Bedrock latency."""
        self.record("llm_latency_seconds", seconds)

    # ------------------------------------------------------------------
    # Timer helpers
    # ------------------------------------------------------------------

    def start_timer(self, name: str) -> None:
        """Start a named timer.

        Args:
            name: Timer name (used with ``stop_timer``).
        """
        self._timers[name] = time.monotonic()

    def stop_timer(self, name: str) -> float:
        """Stop a named timer and record the elapsed duration.

        Args:
            name: Timer name matching a prior ``start_timer`` call.

        Returns:
            Elapsed time in seconds.
        """
        if name not in self._timers:
            return 0.0
        elapsed = time.monotonic() - self._timers.pop(name)
        self.record(name, elapsed)
        return elapsed

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def percentile(self, values: list[float], p: float) -> float:
        """Compute a percentile from a list of values.

        Args:
            values: Observed values.
            p: Percentile (0.0–100.0).

        Returns:
            Percentile value, or 0.0 if list is empty.
        """
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = max(0, int(len(sorted_v) * p / 100) - 1)
        return sorted_v[idx]

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of all counters and histogram percentiles.

        Returns:
            Dict suitable for JSON serialisation in evaluation reports.
        """
        result: dict[str, Any] = {"counters": dict(self._counters), "histograms": {}}
        for name, values in self._histograms.items():
            if values:
                result["histograms"][name] = {
                    "count": len(values),
                    "sum": sum(values),
                    "mean": sum(values) / len(values),
                    "p50": self.percentile(values, 50),
                    "p95": self.percentile(values, 95),
                    "min": min(values),
                    "max": max(values),
                }
        return result

    def log_summary(self) -> None:
        """Print the metrics summary to stdout."""
        import json

        print("[metrics] Pipeline metrics summary:")
        print(json.dumps(self.summary(), indent=2))


# Module-level singleton
metrics = LineageMetrics()
