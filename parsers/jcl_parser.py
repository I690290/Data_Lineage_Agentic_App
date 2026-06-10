"""JCL parser — extracts DD statements and EXEC PGM references."""
from __future__ import annotations

import re

from parsers.models import ChunkMetadata


_JOB_PATTERN = re.compile(r"^//(\w+)\s+JOB\s+(.*)", re.MULTILINE)
_EXEC_PATTERN = re.compile(r"^//(\w+)\s+EXEC\s+(?:PGM=)?([\w.]+)(.*)", re.MULTILINE)
_DD_PATTERN = re.compile(r"^//(\w+)\s+DD\s+(.*)", re.MULTILINE)
_DSN_PATTERN = re.compile(r"DSN=([\w.]+)", re.IGNORECASE)
_STEPNAME_PATTERN = re.compile(r"^//(\w+)\s+EXEC", re.MULTILINE)


class JCLParser:
    """Parse JCL files into structural chunks."""

    def parse(self, file_path: str, source_code: str) -> list[ChunkMetadata]:
        """Parse a JCL file.

        Args:
            file_path: Path to the JCL file.
            source_code: Raw JCL source text.

        Returns:
            List of ChunkMetadata objects.
        """
        lines = source_code.splitlines()
        chunks: list[ChunkMetadata] = []
        dd_map: dict[str, str] = {}

        job_match = _JOB_PATTERN.search(source_code)
        job_name = job_match.group(1) if job_match else "JOB"
        job_chunk = ChunkMetadata(
            file_path=file_path,
            language="JCL",
            ast_path=job_name,
            structural_type="job",
            content=source_code[:500],
            start_line=1,
            end_line=len(lines),
        )
        chunks.append(job_chunk)

        exec_matches = list(_EXEC_PATTERN.finditer(source_code))
        for index, exec_match in enumerate(exec_matches):
            step_name = exec_match.group(1)
            pgm_name = exec_match.group(2).replace("PGM=", "")
            start_pos = exec_match.start()
            end_pos = exec_matches[index + 1].start() if index + 1 < len(exec_matches) else len(source_code)
            step_content = source_code[start_pos:end_pos]
            start_line = source_code[:start_pos].count("\n") + 1
            end_line = source_code[:end_pos].count("\n") + 1

            io_operations: list[dict[str, object]] = []
            for dd_match in _DD_PATTERN.finditer(step_content):
                dd_name = dd_match.group(1)
                dd_value = dd_match.group(2)
                dsn_match = _DSN_PATTERN.search(dd_value)
                dsn = dsn_match.group(1) if dsn_match else dd_value[:40]
                dd_map[dd_name] = dsn
                io_operations.append(
                    {
                        "type": "DD_STATEMENT",
                        "target": dsn,
                        "dd_name": dd_name,
                        "line": start_line + step_content[:dd_match.start()].count("\n"),
                    }
                )

            step_chunk = ChunkMetadata(
                file_path=file_path,
                language="JCL",
                ast_path=f"{job_name}.{step_name}",
                structural_type="step",
                content=step_content,
                start_line=start_line,
                end_line=end_line,
                parent_chunk_id=job_chunk.chunk_id,
            )
            step_chunk.io_operations = io_operations
            step_chunk.data_movements = [
                {"source": "JCL_STEP", "target": pgm_name, "type": "EXEC", "line": start_line}
            ]
            chunks.append(step_chunk)

        job_chunk.io_operations = [{"type": "DD_MAP", "target": str(dd_map), "line": 0}]
        return chunks

    def extract_dd_map(self, source_code: str) -> dict[str, str]:
        """Extract DDNAME -> physical dataset name mapping.

        Args:
            source_code: Raw JCL source text.

        Returns:
            Dict of ``{DD_NAME: DSN}`` pairs.
        """
        dd_map: dict[str, str] = {}
        for dd_match in _DD_PATTERN.finditer(source_code):
            dd_name = dd_match.group(1)
            dd_value = dd_match.group(2)
            dsn_match = _DSN_PATTERN.search(dd_value)
            dd_map[dd_name] = dsn_match.group(1) if dsn_match else dd_value[:60].strip()
        return dd_map
