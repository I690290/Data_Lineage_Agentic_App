"""
Ingestion pipeline:
  1. Walk the repo directory and classify files by extension / content
  2. Chunk each file using the appropriate chunker
  3. Embed chunks using Amazon Titan Embeddings V2 via Bedrock
  4. Store in ChromaDB (persistent) with a SQLite hash cache for incremental runs
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import boto3
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from src.chunkers.cobol_chunker import chunk_cobol_file, chunk_copybook, chunk_jcl_file
from src.chunkers.java_chunker import chunk_java_file, chunk_config_file
from src.config import settings
from src.models import FileChunk

# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------

_EXTENSION_MAP: dict[str, str] = {
    ".cbl": "cobol",
    ".cob": "cobol",
    ".cpy": "copybook",
    ".jcl": "jcl",
    ".java": "java",
    ".sql": "sql",
    ".yml": "config",
    ".yaml": "config",
    ".properties": "config",
}


def classify_file(file_path: str) -> str | None:
    """Return language tag or None if the file should be skipped."""
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_MAP.get(ext)


def walk_repo(repo_path: str) -> list[dict[str, Any]]:
    """Walk the repo and return a list of classified file entries."""
    manifest = []
    skip_dirs = {".git", ".svn", "node_modules", "__pycache__", "target", "build"}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            fpath = os.path.join(root, fname)
            lang = classify_file(fpath)
            if lang:
                manifest.append({"file_path": fpath, "language": lang})
    return manifest


# ---------------------------------------------------------------------------
# Hash cache (SQLite)
# ---------------------------------------------------------------------------

def _init_hash_cache(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS file_hashes "
        "(file_path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, embedded_at TEXT)"
    )
    conn.commit()
    return conn


def _file_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _is_changed(conn: sqlite3.Connection, file_path: str, current_hash: str) -> bool:
    row = conn.execute(
        "SELECT sha256 FROM file_hashes WHERE file_path = ?", (file_path,)
    ).fetchone()
    return row is None or row[0] != current_hash


def _mark_embedded(conn: sqlite3.Connection, file_path: str, file_hash: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO file_hashes (file_path, sha256, embedded_at) "
        "VALUES (?, ?, datetime('now'))",
        (file_path, file_hash),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Titan Embeddings via Bedrock
# ---------------------------------------------------------------------------

class TitanEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function using Titan Embed V2."""

    def __init__(self) -> None:
        session = boto3.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token or None,
            region_name=settings.aws_region,
        )
        self._client = session.client("bedrock-runtime")
        self._model_id = settings.bedrock_embed_model_id

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: Embeddings = []
        for text in input:
            # Titan Embed V2 accepts up to ~8192 tokens; truncate if needed
            truncated = text[: settings.max_chunk_tokens * 4]
            body = json.dumps({"inputText": truncated})
            response = self._client.invoke_model(
                modelId=self._model_id,
                contentType="application/json",
                accept="application/json",
                body=body,
            )
            result = json.loads(response["body"].read())
            embeddings.append(result["embedding"])
        return embeddings


# ---------------------------------------------------------------------------
# ChromaDB setup
# ---------------------------------------------------------------------------

def _get_chroma_collections(embed_fn: TitanEmbeddingFunction):
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    code_col = client.get_or_create_collection(
        name="code_chunks",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    config_col = client.get_or_create_collection(
        name="config_mappings",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return code_col, config_col


def chunk_sql_file(file_path: str) -> list[FileChunk]:
    """Split an Oracle/DB2 SQL file into one chunk per major statement.

    Returns one FileChunk for the whole file plus individual chunks for each
    major CREATE TABLE/VIEW/EXTERNAL, INSERT, LOAD DATA, and UPDATE statement.
    The whole-file chunk is the primary chunk used for LLM column-lineage analysis.
    """
    try:
        content = Path(file_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    stem = Path(file_path).stem.upper()
    chunks: list[FileChunk] = []

    # Primary: whole-file chunk for LLM analysis
    chunks.append(FileChunk(
        file_path=file_path,
        language='sql',
        chunk_type='file',
        chunk_name=stem,
        content=content,
    ))

    # Secondary: one chunk per major statement block (between semicolons)
    import re as _re
    stmts = [s.strip() for s in _re.split(r';\s*\n', content) if s.strip()]
    for i, stmt in enumerate(stmts):
        first_line = stmt.splitlines()[0] if stmt else ''
        # Identify statement type from first keyword
        kw_match = _re.match(
            r'(?:--[^\n]*\n)*\s*'
            r'(CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|EXTERNAL)?|'
            r'INSERT|LOAD|UPDATE|ALTER)',
            stmt, _re.I,
        )
        stmt_type = kw_match.group(1).split()[0].upper() if kw_match else 'STMT'
        chunks.append(FileChunk(
            file_path=file_path,
            language='sql',
            chunk_type=stmt_type.lower(),
            chunk_name=f'{stem}_stmt{i+1}',
            content=stmt,
            metadata={'statement_index': i, 'statement_type': stmt_type},
        ))

    return [c for c in chunks if c.content.strip()]



def chunk_file(file_path: str, language: str) -> list[FileChunk]:
    dispatch = {
        "cobol": chunk_cobol_file,
        "copybook": chunk_copybook,
        "jcl": chunk_jcl_file,
        "java": chunk_java_file,
        "config": chunk_config_file,
        "sql": chunk_sql_file,
    }
    fn = dispatch.get(language)
    if fn is None:
        return []
    try:
        return fn(file_path)
    except Exception as exc:
        print(f"  [WARN] Failed to chunk {file_path}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Main ingestion entry point
# ---------------------------------------------------------------------------

def run_ingestion(repo_path: str | None = None) -> list[dict[str, Any]]:
    """
    Full ingestion pipeline. Returns the file manifest.
    Skips files whose content hash hasn't changed since last run.
    """
    repo = repo_path or settings.repo_path
    print(f"[ingest] Scanning repo: {repo}")

    manifest = walk_repo(repo)
    print(f"[ingest] Found {len(manifest)} source files")

    embed_fn = TitanEmbeddingFunction()
    code_col, config_col = _get_chroma_collections(embed_fn)
    hash_conn = _init_hash_cache(settings.hash_cache_path)

    total_chunks = 0
    skipped_files = 0

    for entry in manifest:
        fpath = entry["file_path"]
        lang = entry["language"]
        file_hash = _file_sha256(fpath)

        if not _is_changed(hash_conn, fpath, file_hash):
            skipped_files += 1
            continue

        chunks = chunk_file(fpath, lang)
        if not chunks:
            continue

        # Drop any chunk whose content is empty — sending an empty string to
        # Bedrock Titan Embed raises ValidationException (minLength: 1).
        chunks = [c for c in chunks if c.content.strip()]
        if not chunks:
            continue

        # Select target collection
        collection = config_col if lang == "config" else code_col

        # Batch upsert into ChromaDB
        ids = [c.doc_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [
            {k: json.dumps(v) if isinstance(v, (list, dict)) else str(v)
             for k, v in c.metadata.items()}
            | {"file_path": c.file_path, "language": c.language,
               "chunk_type": c.chunk_type, "chunk_name": c.chunk_name}
            for c in chunks
        ]

        try:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            _mark_embedded(hash_conn, fpath, file_hash)
            total_chunks += len(chunks)
            print(f"  [OK] {fpath} → {len(chunks)} chunk(s)")
        except Exception as exc:
            print(f"  [ERROR] {fpath}: {exc}")

    hash_conn.close()
    print(
        f"[ingest] Done. {total_chunks} chunks embedded. "
        f"{skipped_files} files unchanged (skipped)."
    )
    return manifest
