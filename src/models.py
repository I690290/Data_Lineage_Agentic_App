"""Shared dataclasses for the ingestion layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
