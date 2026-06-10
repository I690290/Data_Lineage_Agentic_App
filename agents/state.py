"""LangGraph state schema for the ReAct + Reflexion lineage pipeline."""
from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from parsers.models import ChunkMetadata


class LineageState(TypedDict, total=False):
    """Full state for the LangGraph lineage extraction pipeline.

    Attributes:
        file_path: Source file currently being processed.
        language: Detected language of the current file.
        chunks: Parsed ChunkMetadata objects from the parser layer.
        messages: Accumulated LangChain messages (ReAct working memory).
        current_chunk_index: Index into ``chunks`` being processed.
        extracted_assertions: OpenLineage-format assertion dicts produced by agents.
        verification_results: Programmatic verification outcome per assertion.
        retry_count: Current Reflexion retry attempt (max: settings.reflexion_max_retries).
        episodic_memory: Accumulated failure context strings for Reflexion prompting.
        all_file_assertions: All assertions grouped by file_path across the full run.
        verified_lineage: Final verified OpenLineage event dicts.
        needs_human_review: Assertions that failed all retries; need manual review.
        confidence_scores: Mapping of assertion_id to confidence float.
        repo_path: Root path of the repository being analysed.
        file_manifest: Classified file list from repo scan.
        config_map: Datasource bean → schema/table name.
        jcl_dd_map: DDNAME → physical dataset name.
        lineage_nodes: Built LineageNode objects for graph output.
        lineage_edges: Built LineageEdge objects for graph output.
        unresolved_refs: Cross-file references that could not be resolved.
        errors: Accumulated error strings.
        output_json_path: Path where the final JSON was written.
    """

    file_path: str
    language: str
    chunks: list[ChunkMetadata]

    messages: Annotated[list, add_messages]
    current_chunk_index: int
    extracted_assertions: list[dict[str, Any]]

    verification_results: list[dict[str, Any]]
    retry_count: int
    episodic_memory: list[str]

    all_file_assertions: dict[str, list[dict[str, Any]]]

    verified_lineage: list[dict[str, Any]]
    needs_human_review: list[dict[str, Any]]
    confidence_scores: dict[str, float]

    repo_path: str
    file_manifest: list[dict[str, Any]]
    config_map: dict[str, str]
    jcl_dd_map: dict[str, str]
    lineage_nodes: list[Any]
    lineage_edges: list[Any]
    unresolved_refs: list[str]
    errors: list[str]
    output_json_path: str
