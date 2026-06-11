"""Smoke-test all project module imports.

Run via:  uv run python scripts/check_imports.py
Or:       make check-imports
"""
from __future__ import annotations

import sys

MODULES: list[str] = [
    "config.models",
    "config.settings",
    "parsers.models",
    "parsers.orchestrator",
    "parsers.language_detector",
    "embeddings.pipeline",
    "agents.state",
    "agents.pipeline",
    "agents.react_agent",
    "agents.verification",
    "agents.reflexion",
    "agents.cross_language_linker",
    "lineage.openlineage_emitter",
    "graph.schema",
    "graph.writer",
    "observability.tracing",
    "observability.metrics",
    "rag.strands_rag",
    "evaluation.runner",
    "evaluation.golden_dataset_generator",
    "evaluation.level1_assertion",
    "evaluation.level2_file",
    "evaluation.level3_system",
    "models.lineage_models",
]

ok = fail = 0
for mod in MODULES:
    try:
        __import__(mod, fromlist=["_"])
        print(f"  OK  {mod}")
        ok += 1
    except Exception as exc:
        print(f"  ERR {mod}: {exc}")
        fail += 1

print(f"\n  {ok}/{ok + fail} imports OK" + (" ✅" if fail == 0 else f" — {fail} FAILED ❌"))
sys.exit(fail)
