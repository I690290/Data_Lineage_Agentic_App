"""ParserOrchestrator — routes files to language-specific parsers."""
from __future__ import annotations

import os
from pathlib import Path

from parsers.cobol_parser import COBOLParser
from parsers.java_parser import JavaParser
from parsers.jcl_parser import JCLParser
from parsers.language_detector import LanguageDetector
from parsers.models import ChunkMetadata
from parsers.sql_parser import SQLParser


class ParserOrchestrator:
    """Route each file to the appropriate language-specific parser.

    Args:
        cobol_parser: COBOLParser instance.
        java_parser: JavaParser instance.
        sql_parser: SQLParser instance.
        jcl_parser: JCLParser instance.
        detector: LanguageDetector instance.
    """

    def __init__(
        self,
        cobol_parser: COBOLParser | None = None,
        java_parser: JavaParser | None = None,
        sql_parser: SQLParser | None = None,
        jcl_parser: JCLParser | None = None,
        detector: LanguageDetector | None = None,
    ) -> None:
        self._cobol = cobol_parser or COBOLParser()
        self._java = java_parser or JavaParser()
        self._sql = sql_parser or SQLParser()
        self._jcl = jcl_parser or JCLParser()
        self._detector = detector or LanguageDetector()

    def parse_file(self, file_path: str) -> list[ChunkMetadata]:
        """Parse a single file and return its chunks.

        Args:
            file_path: Absolute or relative path to the source file.

        Returns:
            List of ChunkMetadata objects, or empty list if language is unsupported.
        """
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        language, confidence = self._detector.detect(file_path, source)
        if confidence < 0.1:
            return []

        if language in ("COBOL", "copybook"):
            return self._cobol.parse(file_path, source)
        if language == "Java":
            return self._java.parse(file_path, source)
        if language == "SQL":
            return self._sql.parse(file_path, source)
        if language == "JCL":
            return self._jcl.parse(file_path, source)
        return []

    def parse_directory(self, dir_path: str) -> dict[str, list[ChunkMetadata]]:
        """Parse all supported files under a directory recursively.

        Args:
            dir_path: Root directory to walk.

        Returns:
            Dict of ``{file_path: [ChunkMetadata, ...]}``.
        """
        skip_dirs = {".git", "node_modules", "__pycache__", "target", "build", ".venv"}
        results: dict[str, list[ChunkMetadata]] = {}
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [directory for directory in dirs if directory not in skip_dirs]
            for file_name in files:
                file_path = os.path.join(root, file_name)
                chunks = self.parse_file(file_path)
                if chunks:
                    results[file_path] = chunks
        return results
