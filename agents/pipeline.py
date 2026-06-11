"""LangGraph pipeline — ReAct + Reflexion lineage extraction graph."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.cross_language_linker import CrossLanguageLinker
from agents.react_agent import (
    cobol_extraction_agent,
    java_extraction_agent,
    jcl_extraction_agent,
    sql_extraction_agent,
)
from agents.reflexion import ReflexionRetry
from agents.verification import VerificationGate
from lineage.openlineage_emitter import OpenLineageEmitter
from parsers.orchestrator import ParserOrchestrator
from config.settings import settings


_orchestrator = ParserOrchestrator()
_verifier = VerificationGate()
_reflexion = ReflexionRetry(max_retries=settings.reflexion_max_retries)
_emitter = OpenLineageEmitter()

# Load oracle evaluators once at module level (non-fatal if oracle is absent)
try:
    from evaluation.expected_lineage_evaluator import ExpectedLineageEvaluator
    from evaluation.path_evaluator import PathEvaluator
    _expected_eval = ExpectedLineageEvaluator()
    _path_eval = PathEvaluator()
except Exception:
    _expected_eval = None  # type: ignore[assignment]
    _path_eval = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def language_router_node(state: dict[str, Any]) -> dict[str, Any]:
    """Parse current file and detect language; populate ``chunks``.

    Args:
        state: Current LineageState.

    Returns:
        Updated state with ``chunks`` and ``language`` set.
    """
    file_path = state.get("file_path", "")
    if not file_path:
        # Multi-file mode: pick next unprocessed file from manifest
        manifest = state.get("file_manifest", [])
        processed = set((state.get("all_file_assertions") or {}).keys())
        unprocessed = [e for e in manifest if e["file_path"] not in processed and e["language"] not in ("config",)]
        if not unprocessed:
            print("[language_router] All files processed")
            return {**state, "file_path": "", "language": "done", "chunks": []}
        entry = unprocessed[0]
        file_path = entry["file_path"]

    print(f"[language_router] Parsing {file_path}")
    chunks = _orchestrator.parse_file(file_path)
    language = chunks[0].language.lower() if chunks else "unknown"
    print(f"[language_router] {len(chunks)} chunks, language={language}")

    return {
        **state,
        "file_path": file_path,
        "language": language,
        "chunks": chunks,
        "extracted_assertions": [],
        "verification_results": [],
        "retry_count": 0,
        "episodic_memory": [],
        "messages": [],
    }


def verify_assertions_node(state: dict[str, Any]) -> dict[str, Any]:
    """Programmatically verify extracted assertions against source AST.

    Args:
        state: Current LineageState with ``extracted_assertions`` and ``chunks``.

    Returns:
        Updated state with ``verification_results`` populated.
    """
    assertions = state.get("extracted_assertions", [])
    chunks = state.get("chunks", [])
    if not assertions:
        return {**state, "verification_results": []}

    print(f"[verification] Verifying {len(assertions)} assertions")
    results = _verifier.verify(assertions, chunks)
    passed = sum(1 for r in results if r.get("passed", False))
    print(f"[verification] {passed}/{len(results)} assertions passed")
    return {**state, "verification_results": results}


def reflexion_retry_node(state: dict[str, Any]) -> dict[str, Any]:
    """Update episodic memory and increment retry counter.

    Enriches episodic memory with oracle checklist hints (if available) so the
    agent knows exactly which expected lineage elements are still missing.

    Args:
        state: Current LineageState with ``verification_results``.

    Returns:
        Updated state with ``retry_count`` and ``episodic_memory`` updated.
    """
    verification_results = state.get("verification_results", [])
    retry_count = state.get("retry_count", 0)
    print(f"[reflexion] Retry {retry_count + 1}/{settings.reflexion_max_retries}")

    # Gather oracle-based hints for missing expected lineage elements
    checklist_hints: list[str] = []
    if _expected_eval is not None or _path_eval is not None:
        verified = state.get("verified_lineage", [])
        extracted_assertions = state.get("extracted_assertions", [])
        all_assertions = verified + extracted_assertions

        nodes = [
            {"name": a.get("source", {}).get("entity", ""), "id": a.get("source", {}).get("entity", "")}
            for a in all_assertions
        ] + [
            {"name": a.get("target", {}).get("entity", ""), "id": a.get("target", {}).get("entity", "")}
            for a in all_assertions
        ]
        edges = [
            {
                "source": a.get("source", {}).get("entity", ""),
                "target": a.get("target", {}).get("entity", ""),
            }
            for a in all_assertions
        ]

        if _expected_eval is not None:
            checklist_hints.extend(_expected_eval.checklist_hints_for_reflexion(nodes, edges))
        if _path_eval is not None:
            checklist_hints.extend(_path_eval.reflexion_hints(nodes, edges))

    return _reflexion.update_state(state, verification_results, checklist_hints=checklist_hints)


def cross_language_linker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Accumulate verified assertions and resolve cross-language links.

    Args:
        state: Current LineageState.

    Returns:
        Updated state with cross-language assertions added to ``verified_lineage``.
    """
    # Accumulate assertions from the current file
    verified = state.get("verified_lineage", [])
    assertions = state.get("extracted_assertions", [])
    verification_results = state.get("verification_results", [])
    human_review = list(state.get("needs_human_review", []))
    all_file_assertions = dict(state.get("all_file_assertions") or {})

    # Separate passed vs failed
    passed_assertions, failed_assertions = _reflexion.partition_assertions(assertions, verification_results)
    human_review.extend(failed_assertions)

    file_path = state.get("file_path", "")
    language = state.get("language", "unknown")
    if file_path:
        all_file_assertions.setdefault(language, []).extend(passed_assertions)
        all_file_assertions[file_path] = passed_assertions

    verified.extend(passed_assertions)

    # Cross-language linking (only when multiple languages have been processed)
    lang_groups = {
        lang: [a for k, v in all_file_assertions.items() for a in v if k == lang]
        for lang in ("cobol", "java", "sql", "jcl")
    }
    linker = CrossLanguageLinker()
    cross_links = linker.link(lang_groups)
    if cross_links:
        verified.extend(cross_links)
        print(f"[cross_lang_linker] Added {len(cross_links)} cross-language links")

    return {
        **state,
        "verified_lineage": verified,
        "all_file_assertions": all_file_assertions,
        "needs_human_review": human_review,
    }


def openlineage_emitter_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate OpenLineage events from verified assertions.

    Args:
        state: Current LineageState with ``verified_lineage``.

    Returns:
        State unchanged (events are written as a side effect).
    """
    verified = state.get("verified_lineage", [])
    if not verified:
        return state

    file_path = state.get("file_path", "unknown")
    language = state.get("language", "unknown").upper()
    events = _emitter.emit_from_assertions(verified, language, file_path)

    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(file_path).stem if file_path else "combined"
    out_path = output_dir / f"{stem}_lineage.json"
    _emitter.to_file(events, str(out_path))
    print(f"[openlineage_emitter] {len(events)} events → {out_path}")
    return state


def neo4j_writer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Persist verified lineage to Neo4j.

    Args:
        state: Current LineageState with ``verified_lineage``.

    Returns:
        State with any errors appended.
    """
    verified = state.get("verified_lineage", [])
    errors = list(state.get("errors", []))

    if not verified:
        return state

    file_path = state.get("file_path", "unknown")
    language = state.get("language", "unknown").upper()

    try:
        from graph.writer import Neo4jLineageWriter

        writer = Neo4jLineageWriter(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        events = _emitter.emit_from_assertions(verified, language, file_path)
        writer.upsert_lineage(events)
        writer.close()
        print(f"[neo4j_writer] Persisted {len(verified)} assertions to Neo4j")
    except Exception as exc:
        msg = f"Neo4j write error for {file_path}: {exc}"
        print(f"[neo4j_writer] {msg}")
        errors.append(msg)

    return {**state, "errors": errors}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_by_language(state: dict[str, Any]) -> str:
    """Route to the correct language-specific agent.

    Args:
        state: Current LineageState with ``language`` set.

    Returns:
        Node name string for the LangGraph router.
    """
    language = (state.get("language") or "").lower()
    if language in ("cobol", "copybook"):
        return "cobol_agent"
    if language == "java":
        return "java_agent"
    if language == "sql":
        return "sql_agent"
    if language == "jcl":
        return "jcl_agent"
    # config, unknown → skip extraction, go to linker directly
    return "cross_language_linker"


def should_retry_or_proceed(state: dict[str, Any]) -> str:
    """Decide whether to retry extraction or proceed to cross-language linking.

    Args:
        state: Current LineageState with ``verification_results`` and ``retry_count``.

    Returns:
        ``"retry"`` or ``"proceed"``.
    """
    verification_results = state.get("verification_results", [])
    retry_count = state.get("retry_count", 0)

    if _verifier.should_retry(verification_results, retry_count, settings.reflexion_max_retries):
        return "retry"
    return "proceed"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_pipeline() -> Any:
    """Build and compile the full ReAct + Reflexion LangGraph pipeline.

    Returns:
        Compiled LangGraph ``StateGraph`` with ``MemorySaver`` checkpointer.
    """
    from agents.state import LineageState

    graph = StateGraph(LineageState)

    # Register all nodes
    graph.add_node("language_router", language_router_node)
    graph.add_node("cobol_agent", cobol_extraction_agent)
    graph.add_node("java_agent", java_extraction_agent)
    graph.add_node("sql_agent", sql_extraction_agent)
    graph.add_node("jcl_agent", jcl_extraction_agent)
    graph.add_node("verification_gate", verify_assertions_node)
    graph.add_node("reflexion_retry", reflexion_retry_node)
    graph.add_node("cross_language_linker", cross_language_linker_node)
    graph.add_node("openlineage_emitter", openlineage_emitter_node)
    graph.add_node("neo4j_writer", neo4j_writer_node)

    # Entry point
    graph.set_entry_point("language_router")

    # Language routing conditional edges
    graph.add_conditional_edges(
        "language_router",
        route_by_language,
        {
            "cobol_agent": "cobol_agent",
            "java_agent": "java_agent",
            "sql_agent": "sql_agent",
            "jcl_agent": "jcl_agent",
            "cross_language_linker": "cross_language_linker",
        },
    )

    # All language agents → verification
    for agent_node in ("cobol_agent", "java_agent", "sql_agent", "jcl_agent"):
        graph.add_edge(agent_node, "verification_gate")

    # Verification → conditional: retry or proceed
    graph.add_conditional_edges(
        "verification_gate",
        should_retry_or_proceed,
        {
            "retry": "reflexion_retry",
            "proceed": "cross_language_linker",
        },
    )

    # Reflexion loop back to verification (re-invokes the same language agent)
    graph.add_edge("reflexion_retry", "verification_gate")

    # Linear tail
    graph.add_edge("cross_language_linker", "openlineage_emitter")
    graph.add_edge("openlineage_emitter", "neo4j_writer")
    graph.add_edge("neo4j_writer", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


def run_pipeline(repo_path: str | None = None) -> dict[str, Any]:
    """Run the full lineage extraction pipeline over a repository.

    Args:
        repo_path: Root path to analyse; defaults to ``settings.repo_path``.

    Returns:
        Final LineageState dict after pipeline completion.
    """
    from src.ingest import walk_repo

    rpath = repo_path or settings.repo_path
    manifest = walk_repo(rpath)
    print(f"[pipeline] Found {len(manifest)} files in {rpath}")

    compiled = build_pipeline()
    initial_state: dict[str, Any] = {
        "repo_path": rpath,
        "file_manifest": manifest,
        "file_path": "",
        "language": "",
        "chunks": [],
        "messages": [],
        "current_chunk_index": 0,
        "extracted_assertions": [],
        "verification_results": [],
        "retry_count": 0,
        "episodic_memory": [],
        "all_file_assertions": {},
        "verified_lineage": [],
        "needs_human_review": [],
        "confidence_scores": {},
        "config_map": {},
        "jcl_dd_map": {},
        "lineage_nodes": [],
        "lineage_edges": [],
        "unresolved_refs": [],
        "errors": [],
        "output_json_path": "",
    }

    config = {"configurable": {"thread_id": "lineage-run-1"}}
    final_state = compiled.invoke(initial_state, config=config)
    print(
        f"[pipeline] Done. Verified={len(final_state.get('verified_lineage', []))} "
        f"HumanReview={len(final_state.get('needs_human_review', []))} "
        f"Errors={len(final_state.get('errors', []))}"
    )
    return final_state
