from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import boto3

from config.settings import settings
from parsers.models import ChunkMetadata

_COLLECTION_NAMES: dict[str, str] = {
    "cobol": "cobol_chunks",
    "java": "java_chunks",
    "sql": "sql_chunks",
}


class EmbeddingPipeline:
    """Embed parsed chunks into ChromaDB and execute semantic search.

    Args:
        bedrock_client: boto3 Bedrock Runtime client. If ``None``, one is created
            from ``config.settings``.
        chromadb_client: ChromaDB client. If ``None``, a persistent client is created
            using the configured storage directory.
    """

    def __init__(self, bedrock_client: Any | None, chromadb_client: Any | None) -> None:
        self._bedrock = bedrock_client or self._create_bedrock_client()
        self._chromadb = chromadb_client or self._create_chromadb_client()
        self._model_id = settings.bedrock_embed_model_id or "amazon.titan-embed-text-v2:0"
        self._collections = {
            language: self._chromadb.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            for language, collection_name in _COLLECTION_NAMES.items()
        }

    def embed_chunks(self, chunks: list[ChunkMetadata]) -> None:
        """Embed and upsert chunks into per-language ChromaDB collections.

        Args:
            chunks: Parsed structural chunks.

        Raises:
            RuntimeError: If one or more chunks could not be embedded or stored.
        """
        if not chunks:
            return

        grouped: dict[str, list[ChunkMetadata]] = {key: [] for key in _COLLECTION_NAMES}
        unsupported: list[str] = []
        for chunk in chunks:
            language = self._normalise_language(chunk.language)
            if language not in grouped:
                unsupported.append(f"{chunk.file_path}:{chunk.language}")
                continue
            grouped[language].append(chunk)

        errors: list[str] = []
        for language, language_chunks in grouped.items():
            if not language_chunks:
                continue
            ids: list[str] = []
            documents: list[str] = []
            metadatas: list[dict[str, Any]] = []
            embeddings: list[list[float]] = []

            for chunk in language_chunks:
                try:
                    embedding = self._embed_text(chunk.content)
                    ids.append(chunk.chunk_id)
                    documents.append(chunk.content)
                    metadatas.append(self._build_metadata(chunk))
                    embeddings.append(embedding)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Failed to embed {chunk.file_path} [{chunk.ast_path}]: {exc}")

            if not ids:
                continue

            try:
                self._collections[language].upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"Failed to upsert {len(ids)} {language} chunk(s) into "
                    f"{_COLLECTION_NAMES[language]}: {exc}"
                )

        if unsupported:
            errors.append(
                "Unsupported chunk language(s): " + ", ".join(sorted(set(unsupported)))
            )

        if errors:
            raise RuntimeError("; ".join(errors))

    def search(
        self,
        query: str,
        language: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search embedded chunks by semantic similarity.

        Args:
            query: Natural-language or code search query.
            language: Optional language filter (``COBOL``, ``Java``, ``SQL``).
            top_k: Maximum number of hits to return.

        Returns:
            Ranked search results with metadata and distances.
        """
        if not query.strip() or top_k <= 0:
            return []

        query_embedding = self._embed_text(query)
        languages = [self._normalise_language(language)] if language else list(self._collections)
        results: list[dict[str, Any]] = []

        for lang in languages:
            if lang not in self._collections:
                continue
            try:
                raw = self._collections[lang].query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"ChromaDB query failed for collection {_COLLECTION_NAMES[lang]}: {exc}"
                ) from exc
            results.extend(self._query_to_results(raw, lang))

        results.sort(key=lambda item: item.get("distance", 1.0))
        return results[:top_k]

    def search_by_ast_path(self, ast_path_prefix: str) -> list[dict[str, Any]]:
        """Return all chunks whose AST path starts with the supplied prefix.

        Args:
            ast_path_prefix: Prefix to match against stored ``ast_path`` metadata.

        Returns:
            Matching chunk documents and metadata across all collections.
        """
        prefix = ast_path_prefix.strip().lower()
        if not prefix:
            return []

        matches: list[dict[str, Any]] = []
        for language, collection in self._collections.items():
            try:
                raw = collection.get(include=["documents", "metadatas"])
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Failed to read collection {_COLLECTION_NAMES[language]}: {exc}"
                ) from exc

            ids = raw.get("ids", []) or []
            documents = raw.get("documents", []) or []
            metadatas = raw.get("metadatas", []) or []
            for chunk_id, document, metadata in zip(ids, documents, metadatas, strict=False):
                ast_path = str((metadata or {}).get("ast_path", ""))
                if ast_path.lower().startswith(prefix):
                    matches.append(
                        self._result_record(
                            chunk_id=chunk_id,
                            document=document,
                            metadata=metadata or {},
                            distance=None,
                            language=language,
                        )
                    )

        matches.sort(
            key=lambda item: (
                str(item.get("file_path", "")),
                int(item.get("start_line") or 0),
                str(item.get("ast_path", "")),
            )
        )
        return matches

    def _create_bedrock_client(self) -> Any:
        """Create a Bedrock Runtime client from configured settings."""
        session_kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            session_kwargs.update(
                {
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                }
            )
            if settings.aws_session_token:
                session_kwargs["aws_session_token"] = settings.aws_session_token
        elif getattr(settings, "aws_profile", ""):
            session_kwargs["profile_name"] = settings.aws_profile
        session = boto3.Session(**session_kwargs)
        return session.client("bedrock-runtime")

    def _create_chromadb_client(self) -> Any:
        """Create a persistent ChromaDB client from configured settings."""
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - dependency controlled by project
            raise RuntimeError("chromadb is required for EmbeddingPipeline") from exc
        persist_dir = getattr(settings, "chromadb_persist_dir", "") or settings.chroma_persist_dir
        return chromadb.PersistentClient(path=persist_dir)

    def _embed_text(self, text: str) -> list[float]:
        """Generate a Titan embedding for one text payload."""
        truncated = text[: max(1, settings.max_chunk_tokens) * 4]
        request_body = json.dumps({"inputText": truncated})
        try:
            response = self._bedrock.invoke_model(
                modelId=self._model_id,
                contentType="application/json",
                accept="application/json",
                body=request_body,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock invoke_model failed for {self._model_id}: {exc}") from exc

        body = response.get("body")
        if body is None:
            raise RuntimeError("Bedrock response did not include a response body")

        payload = body.read() if hasattr(body, "read") else body
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid Titan embedding response: {payload!r}") from exc

        embedding = data.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError("Titan embedding response missing non-empty 'embedding' vector")
        return [float(value) for value in embedding]

    def _build_metadata(self, chunk: ChunkMetadata) -> dict[str, Any]:
        """Build a flat metadata payload compatible with ChromaDB storage."""
        metadata = chunk.to_metadata_dict()
        metadata["namespace"] = (
            f"{self._normalise_language(chunk.language)}/"
            f"{Path(chunk.file_path).stem}/"
            f"{chunk.structural_type}"
        )
        metadata["parent_chunk_id"] = metadata.get("parent_chunk_id") or ""
        metadata["dependencies"] = self._json_string(chunk.dependencies)
        metadata["io_operations"] = self._json_string(chunk.io_operations)
        metadata["data_movements"] = self._json_string(chunk.data_movements)
        return metadata

    def _query_to_results(self, raw: dict[str, Any], language: str) -> list[dict[str, Any]]:
        """Convert a raw ChromaDB query payload into a flat list of results."""
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        results: list[dict[str, Any]] = []
        for chunk_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=False,
        ):
            results.append(
                self._result_record(
                    chunk_id=chunk_id,
                    document=document,
                    metadata=metadata or {},
                    distance=distance,
                    language=language,
                )
            )
        return results

    def _result_record(
        self,
        *,
        chunk_id: str,
        document: str,
        metadata: dict[str, Any],
        distance: float | None,
        language: str,
    ) -> dict[str, Any]:
        """Create a normalised search result dict."""
        return {
            "chunk_id": chunk_id,
            "document": document,
            "distance": None if distance is None else float(distance),
            "score": None if distance is None else max(0.0, 1.0 - float(distance)),
            "collection": _COLLECTION_NAMES[language],
            "language": metadata.get("language", language.upper()),
            **metadata,
        }

    @staticmethod
    def _json_string(value: Any) -> str:
        """Serialise complex metadata values to JSON strings."""
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError as exc:
            raise RuntimeError(f"Metadata is not JSON serialisable: {value!r}") from exc

    @staticmethod
    def _normalise_language(language: str | None) -> str:
        """Normalise language tags to collection keys."""
        return (language or "").strip().lower()
