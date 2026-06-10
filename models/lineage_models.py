"""Extended lineage dataclasses for column-level lineage and RAG."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnLineageRecord:
    """One field-to-field lineage mapping."""

    source_file: str          # entity name read by the program (reads_from)
    source_column: str
    transformation_name: str
    transformation_type: str
    transformation_code_snippet: str
    target_file: str          # entity name written by the program (writes_to)
    target_column: str
    program_file_path: str = ""  # actual source code file path (e.g. ./mock_code/cobol/PROG.cbl)
    program_name: str = ""       # source code file stem in UPPER (e.g. CRDB2EXT, MI4014_EXT_TABLE)
    confidence_score: float = 0.5
    low_confidence: bool = False

    def __post_init__(self) -> None:
        """Mark records below the confidence threshold."""
        self.low_confidence = self.confidence_score < 0.6


@dataclass
class RetrievedChunk:
    """A single retrieved context chunk from the hybrid retriever."""

    text: str
    source: str
    chunk_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    bm25_score: float = 0.0
    vector_score: float = 0.0
    graph_proximity_score: float = 0.0
    final_score: float = 0.0
    content_hash: str = ""

    def __post_init__(self) -> None:
        """Populate a stable content hash when not provided."""
        if not self.content_hash:
            import hashlib

            self.content_hash = hashlib.md5(
                f"{self.source}::{self.text[:200]}".encode()
            ).hexdigest()


@dataclass
class Citation:
    """A single citation in a RAG answer."""

    key: str
    source_file: str
    chunk_type: str
    snippet: str


@dataclass
class RagAnswer:
    """Output from the answer generator."""

    answer_text: str
    citations: list[Citation] = field(default_factory=list)
