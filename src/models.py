"""Shared dataclasses for the data lineage agentic app."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from typing_extensions import TypedDict

from models.lineage_models import ColumnLineageRecord


@dataclass
class FileChunk:
    """A parsed chunk of source code ready for embedding."""

    file_path: str
    language: str
    chunk_type: str
    chunk_name: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        """Stable ID used as the ChromaDB document ID."""
        import hashlib

        raw = f"{self.file_path}::{self.chunk_type}::{self.chunk_name}"
        return hashlib.md5(raw.encode()).hexdigest()


@dataclass
class LineageNode:
    """A node in the lineage graph."""

    node_id: str
    label: str
    node_type: str
    entity_subtype: str
    name: str
    system: str
    schema_name: str = ""
    file_path: str = ""
    language: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageEdge:
    """A directed relationship between two lineage nodes."""

    edge_id: str
    source_id: str
    target_id: str
    relationship: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Raw analysis output from the text model for one file."""

    file_path: str
    language: str
    reads_from: list[str] = field(default_factory=list)
    writes_to: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    transformations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_output: str = ""
    errors: list[str] = field(default_factory=list)


class AgentState(TypedDict, total=False):
    """LangGraph state shared across all pipeline nodes."""

    repo_path: str
    file_manifest: list[dict[str, Any]]
    config_map: dict[str, str]
    jcl_dd_map: dict[str, str]
    analysis_results: dict[str, AnalysisResult]
    lineage_nodes: list[LineageNode]
    lineage_edges: list[LineageEdge]
    unresolved_refs: list[str]
    errors: list[str]
    output_json_path: str
    column_lineage_records: list[ColumnLineageRecord]
