"""End-to-end lineage path evaluation — catches broken chains per-edge F1 misses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DEFAULT_ORACLE = Path(__file__).parent.parent / "mock_code" / "expected_lineage" / "expected_lineage.json"


class PathResult:
    """Outcome of a single end-to-end path check."""

    def __init__(
        self,
        path_name: str,
        expected_path: list[str],
        found_hops: list[str],
        missing_hops: list[str],
        first_break_index: int | None,
        passed: bool,
    ) -> None:
        self.path_name = path_name
        self.expected_path = expected_path
        self.found_hops = found_hops
        self.missing_hops = missing_hops
        self.first_break_index = first_break_index
        self.passed = passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_name": self.path_name,
            "expected_path": self.expected_path,
            "found_hops": self.found_hops,
            "missing_hops": self.missing_hops,
            "first_break_index": self.first_break_index,
            "hop_completeness": round(len(self.found_hops) / len(self.expected_path), 4) if self.expected_path else 1.0,
            "passed": self.passed,
        }

    def reflexion_hint(self) -> str | None:
        """Return a hint string for Reflexion episodic memory, or None if path passed."""
        if self.passed:
            return None
        if self.first_break_index is not None:
            before = self.expected_path[self.first_break_index - 1] if self.first_break_index > 0 else "START"
            broken = self.expected_path[self.first_break_index]
            return (
                f"PATH BREAK in '{self.path_name}': chain breaks at hop {self.first_break_index} — "
                f"'{before}' → '{broken}' edge is missing. "
                f"Missing nodes: {self.missing_hops}. "
                f"Check the code that connects these two entities and add the missing lineage assertion."
            )
        return (
            f"PATH INCOMPLETE for '{self.path_name}': "
            f"missing hops: {self.missing_hops}."
        )


class PathEvaluator:
    """Evaluate end-to-end lineage paths from the oracle against extracted graph.

    Works at the **graph topology** level: given the extracted nodes and edges,
    check whether every expected end-to-end path from the oracle JSON is present
    as a connected chain.  Individual edge F1 scores can be high while paths are
    still broken at a single intermediate hop — this catches that.

    Args:
        oracle_path: Path to ``expected_lineage.json``.  Defaults to the
            project-bundled oracle under ``mock_code/expected_lineage/``.
    """

    def __init__(self, oracle_path: str | Path | None = None) -> None:
        path = Path(oracle_path) if oracle_path else _DEFAULT_ORACLE
        oracle = json.loads(path.read_text(encoding="utf-8"))
        self._expected_edges: list[dict[str, Any]] = oracle.get("lineage_edges", [])
        # Build named end-to-end paths from lineage_edges (source-chained walk)
        self._named_paths: list[dict[str, Any]] = self._build_named_paths(oracle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Check all oracle end-to-end paths against extracted graph.

        Args:
            extracted_nodes: Nodes from pipeline output (``name`` or ``id`` key).
            extracted_edges: Edges from pipeline output (``source``/``target`` keys).

        Returns:
            Dict with per-path results, completeness score, and reflexion hints.
        """
        adj = self._build_adjacency(extracted_nodes, extracted_edges)
        path_results: list[PathResult] = []
        for path_spec in self._named_paths:
            result = self._check_path(path_spec, adj, extracted_nodes)
            path_results.append(result)

        passed = sum(1 for r in path_results if r.passed)
        total = len(path_results)
        hints = [r.reflexion_hint() for r in path_results if not r.passed and r.reflexion_hint()]

        return {
            "total_paths": total,
            "paths_passed": passed,
            "paths_failed": total - passed,
            "path_completeness": round(passed / total, 4) if total else 1.0,
            "overall_passed": passed == total,
            "results": [r.to_dict() for r in path_results],
            "reflexion_hints": hints,
        }

    def reflexion_hints(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
    ) -> list[str]:
        """Return only the reflexion hint strings for failed paths."""
        report = self.evaluate(extracted_nodes, extracted_edges)
        return report["reflexion_hints"]

    # ------------------------------------------------------------------
    # Path construction from oracle edges
    # ------------------------------------------------------------------

    def _build_named_paths(self, oracle: dict[str, Any]) -> list[dict[str, Any]]:
        """Derive named end-to-end paths by chaining oracle lineage_edges."""
        edges = oracle.get("lineage_edges", [])
        nodes_by_id = {n["id"]: n for n in oracle.get("lineage_nodes", [])}

        # Build adjacency from expected edges
        next_map: dict[str, list[str]] = {}
        prev_set: set[str] = set()
        for e in edges:
            src, tgt = e.get("source", ""), e.get("target", "")
            next_map.setdefault(src, []).append(tgt)
            prev_set.add(tgt)

        # Start nodes: sources that are never targets
        starts = [s for s in next_map if s not in prev_set]
        paths = []
        for start in starts:
            path_nodes = self._dfs_paths(start, next_map)
            for path in path_nodes:
                named = [nodes_by_id.get(nid, {}).get("name", nid) for nid in path]
                paths.append({"node_ids": path, "named": named})

        # Fallback: if no paths were derived, use the edges as pairs
        if not paths:
            for e in edges:
                src_name = nodes_by_id.get(e["source"], {}).get("name", e["source"])
                tgt_name = nodes_by_id.get(e["target"], {}).get("name", e["target"])
                paths.append({
                    "node_ids": [e["source"], e["target"]],
                    "named": [src_name, tgt_name],
                })
        return paths

    def _dfs_paths(self, start: str, next_map: dict[str, list[str]]) -> list[list[str]]:
        """DFS walk from start following next_map; returns all simple paths."""
        paths: list[list[str]] = []
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            nexts = next_map.get(node, [])
            if not nexts:
                paths.append(path)
                continue
            for nxt in nexts:
                if nxt not in path:  # avoid cycles
                    stack.append((nxt, path + [nxt]))
        return paths

    # ------------------------------------------------------------------
    # Path checking
    # ------------------------------------------------------------------

    def _check_path(
        self,
        path_spec: dict[str, Any],
        adj: dict[str, set[str]],
        extracted_nodes: list[dict[str, Any]],
    ) -> PathResult:
        named_path: list[str] = path_spec["named"]
        path_label = f"{named_path[0]} → {named_path[-1]}" if named_path else "empty"
        if len(named_path) < 2:
            return PathResult(path_label, named_path, named_path, [], None, True)

        found_hops: list[str] = [named_path[0]]
        missing_hops: list[str] = []
        first_break: int | None = None
        extracted_name_set = {
            str(n.get("name") or n.get("id") or "").upper() for n in extracted_nodes
        }

        for i in range(len(named_path) - 1):
            src = named_path[i]
            tgt = named_path[i + 1]
            edge_found = self._edge_exists(src, tgt, adj)
            if edge_found:
                found_hops.append(tgt)
            else:
                missing_hops.append(tgt)
                if first_break is None:
                    first_break = i + 1

        passed = len(missing_hops) == 0
        return PathResult(
            path_name=path_label,
            expected_path=named_path,
            found_hops=found_hops,
            missing_hops=missing_hops,
            first_break_index=first_break,
            passed=passed,
        )

    # ------------------------------------------------------------------
    # Adjacency helpers
    # ------------------------------------------------------------------

    def _build_adjacency(
        self,
        extracted_nodes: list[dict[str, Any]],
        extracted_edges: list[dict[str, Any]],
    ) -> dict[str, set[str]]:
        """Build a normalised (uppercase) adjacency set from extracted data."""
        adj: dict[str, set[str]] = {}
        node_id_to_name: dict[str, str] = {}
        for node in extracted_nodes:
            nid = str(node.get("id") or node.get("node_id") or "").upper()
            nname = str(node.get("name") or nid).upper()
            node_id_to_name[nid] = nname

        for edge in extracted_edges:
            src_raw = str(edge.get("source") or "").upper()
            tgt_raw = str(edge.get("target") or "").upper()
            src = node_id_to_name.get(src_raw, src_raw)
            tgt = node_id_to_name.get(tgt_raw, tgt_raw)
            adj.setdefault(src, set()).add(tgt)

        return adj

    def _edge_exists(self, src: str, tgt: str, adj: dict[str, set[str]]) -> bool:
        """Check if an edge src→tgt exists (tolerant fuzzy match)."""
        src_u = src.upper()
        tgt_u = tgt.upper()
        for adj_src, adj_tgts in adj.items():
            if src_u not in adj_src and adj_src not in src_u:
                continue
            for adj_tgt in adj_tgts:
                if tgt_u in adj_tgt or adj_tgt in tgt_u:
                    return True
        return False
