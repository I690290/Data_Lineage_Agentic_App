"""Rule-based language detector — no LLM involved."""
from __future__ import annotations

import re
from pathlib import Path


_EXTENSION_MAP: dict[str, str] = {
    ".cbl": "COBOL",
    ".cob": "COBOL",
    ".cpy": "copybook",
    ".jcl": "JCL",
    ".proc": "JCL",
    ".java": "Java",
    ".sql": "SQL",
    ".ddl": "SQL",
    ".dml": "SQL",
    ".yml": "config",
    ".yaml": "config",
    ".properties": "config",
}

_COBOL_HEURISTICS = re.compile(
    r"\b(IDENTIFICATION DIVISION|PROCEDURE DIVISION|DATA DIVISION|ENVIRONMENT DIVISION)\b",
    re.IGNORECASE,
)
_JCL_HEURISTICS = re.compile(r"^//\w+\s+(JOB|EXEC|DD)\s", re.MULTILINE)
_JAVA_HEURISTICS = re.compile(r"\bpublic\s+(class|interface|enum)\b")
_SQL_HEURISTICS = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE)\b", re.IGNORECASE)


class LanguageDetector:
    """Detect source language from file path and optionally file content."""

    def detect(self, file_path: str, content: str | None = None) -> tuple[str, float]:
        """Return ``(language, confidence)`` for the given file.

        Args:
            file_path: Path to the source file (used for extension matching).
            content: Optional file content for heuristic confirmation.

        Returns:
            Tuple of language string and confidence score (0.0–1.0).
        """
        ext = Path(file_path).suffix.lower()
        if ext in _EXTENSION_MAP:
            lang = _EXTENSION_MAP[ext]
            if content is None:
                return lang, 0.9
            confirmed = self._confirm_with_heuristics(lang, content)
            return lang, 1.0 if confirmed else 0.7

        if content:
            return self._detect_from_content(content)

        return "unknown", 0.0

    def _confirm_with_heuristics(self, language: str, content: str) -> bool:
        """Confirm an extension-based detection with content heuristics."""
        if language == "COBOL":
            return bool(_COBOL_HEURISTICS.search(content))
        if language == "JCL":
            return bool(_JCL_HEURISTICS.search(content))
        if language == "Java":
            return bool(_JAVA_HEURISTICS.search(content))
        if language == "SQL":
            return bool(_SQL_HEURISTICS.search(content))
        return True

    def _detect_from_content(self, content: str) -> tuple[str, float]:
        """Detect language purely from content when extension is ambiguous."""
        if _COBOL_HEURISTICS.search(content):
            return "COBOL", 0.8
        if _JCL_HEURISTICS.search(content):
            return "JCL", 0.85
        if _JAVA_HEURISTICS.search(content):
            return "Java", 0.8
        if _SQL_HEURISTICS.search(content):
            return "SQL", 0.75
        return "unknown", 0.1
