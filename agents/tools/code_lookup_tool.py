"""Code lookup tool — retrieve raw source code by file path and line range."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool


@tool
def code_lookup_tool(
    file_path: Annotated[str, "Absolute or relative path to the source file"],
    start_line: Annotated[int, "1-based start line number (0 = beginning of file)"] = 0,
    end_line: Annotated[int, "1-based end line number (0 = end of file)"] = 0,
) -> str:
    """Retrieve raw source code from a specific file and optional line range.

    Returns JSON with file_path and content. Use to verify exact line numbers
    cited in lineage assertions before confirming them.
    """
    from src.config import settings

    try:
        path = Path(file_path)
        if not path.exists():
            path = Path(settings.repo_path) / file_path
        if not path.exists():
            return json.dumps({"error": f"File not found: {file_path}"})
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if start_line > 0 or end_line > 0:
            start = max(0, start_line - 1)
            end = end_line if end_line > 0 else len(lines)
            lines = lines[start:end]
        return json.dumps({"file_path": str(path), "content": "\n".join(lines)})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
