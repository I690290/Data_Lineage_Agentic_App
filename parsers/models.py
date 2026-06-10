"""ChunkMetadata dataclass used by all language parsers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChunkMetadata:
    """A structural chunk from a parsed source file, ready for embedding.

    Attributes:
        chunk_id: Deterministic SHA-256 hash of (file_path + ast_path + content).
        file_path: Absolute or repo-relative source file path.
        language: Source language tag.
        ast_path: Hierarchical dot-separated path in the AST, e.g. ``"PROCEDURE.MAIN_PARA"``.
        parent_chunk_id: chunk_id of the enclosing structural unit, or None for top-level.
        dependencies: List of referenced chunk IDs (COPY members, imports, called programs).
        token_count: Approximate token count for the embedding model.
        start_line: 1-based source line number where this chunk starts.
        end_line: 1-based source line number where this chunk ends.
        structural_type: Structural category (e.g. ``"division"``, ``"paragraph"``, ``"method"``).
        io_operations: List of I/O operations extracted from this chunk.
            Each entry: ``{"type": "READ", "target": "ACCOUNT-FILE", "line": 142}``.
        data_movements: List of data movement operations.
            Each entry: ``{"source": "ACCT-NUM", "target": "WS-ACCT", "type": "MOVE", "line": 155}``.
        content: Raw source text for this chunk.
    """

    file_path: str
    language: Literal["COBOL", "Java", "SQL", "JCL", "copybook"]
    ast_path: str
    structural_type: str
    content: str
    start_line: int = 0
    end_line: int = 0
    parent_chunk_id: str | None = None
    dependencies: list[str] = field(default_factory=list)
    io_operations: list[dict[str, Any]] = field(default_factory=list)
    data_movements: list[dict[str, Any]] = field(default_factory=list)
    chunk_id: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Compute deterministic chunk_id from file + ast_path + content hash."""
        content_hash = hashlib.sha256(self.content.encode("utf-8", errors="replace")).hexdigest()[:16]
        raw = f"{self.file_path}::{self.ast_path}::{content_hash}"
        self.chunk_id = hashlib.sha256(raw.encode()).hexdigest()

    @property
    def token_count(self) -> int:
        """Approximate token count (4 chars ≈ 1 token)."""
        return max(1, len(self.content) // 4)

    def to_metadata_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict suitable for ChromaDB metadata storage."""
        return {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "language": self.language,
            "ast_path": self.ast_path,
            "parent_chunk_id": self.parent_chunk_id or "",
            "structural_type": self.structural_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "token_count": self.token_count,
            "dependencies": json.dumps(self.dependencies),
            "io_operations": json.dumps(self.io_operations),
            "data_movements": json.dumps(self.data_movements),
        }
