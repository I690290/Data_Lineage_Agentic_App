"""
COBOL chunker — splits COBOL source files into paragraph/section/copybook chunks
using regex-based parsing (tree-sitter COBOL grammar is less mature).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from src.models import FileChunk


# Matches a paragraph or section header in COBOL (columns 8–72, areas A/B)
_PARAGRAPH_RE = re.compile(
    r"^[ ]{6,7}([A-Z0-9][A-Z0-9\-]*)(?:\s+SECTION)?\s*\.\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Matches COPY statements: COPY copybook-name [REPLACING ...].
_COPY_RE = re.compile(
    r"\bCOPY\s+([A-Z0-9][A-Z0-9\-]*)\b",
    re.IGNORECASE,
)

# Matches SELECT ... ASSIGN TO ddname
_SELECT_RE = re.compile(
    r"\bSELECT\s+([A-Z0-9][A-Z0-9\-]*)\s+ASSIGN\s+TO\s+([A-Z0-9][A-Z0-9\-]*)",
    re.IGNORECASE,
)

# Matches CALL 'PROGRAM-NAME'
_CALL_RE = re.compile(
    r"\bCALL\s+['\"]([A-Z0-9][A-Z0-9\-]*)['\"]",
    re.IGNORECASE,
)

# Matches FD entries (file descriptions)
_FD_RE = re.compile(
    r"^\s+FD\s+([A-Z0-9][A-Z0-9\-]*)",
    re.MULTILINE | re.IGNORECASE,
)

# Division headers — used to split the file into top-level sections
_DIVISION_RE = re.compile(
    r"^[ ]{6,7}([A-Z]+\s+DIVISION)\s*\.\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_program_id(source: str) -> str:
    m = re.search(r"\bPROGRAM-ID\s*\.\s*([A-Z0-9][A-Z0-9\-]*)", source, re.IGNORECASE)
    return m.group(1).upper() if m else "UNKNOWN"


def _split_into_paragraphs(source: str) -> list[tuple[str, int, int]]:
    """
    Returns list of (paragraph_name, start_line_idx, end_line_idx) tuples.
    Only includes paragraphs in the PROCEDURE DIVISION.
    """
    lines = source.splitlines()

    # Find PROCEDURE DIVISION start
    proc_start = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s+PROCEDURE\s+DIVISION", line, re.IGNORECASE):
            proc_start = i
            break

    paragraphs: list[tuple[str, int, int]] = []
    current_name: str | None = None
    current_start: int = proc_start

    for i in range(proc_start, len(lines)):
        stripped = lines[i].rstrip()
        m = re.match(
            r"^[ ]{6,7}([A-Z0-9][A-Z0-9\-]*)(?:\s+SECTION)?\s*\.\s*$",
            stripped,
            re.IGNORECASE,
        )
        if m:
            if current_name is not None:
                paragraphs.append((current_name, current_start, i - 1))
            current_name = m.group(1).upper()
            current_start = i

    if current_name is not None:
        paragraphs.append((current_name, current_start, len(lines) - 1))

    return paragraphs


def chunk_cobol_file(file_path: str) -> list[FileChunk]:
    """Parse a COBOL .cbl or .cob file and return a list of FileChunk objects."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    program_id = _extract_program_id(source)

    chunks: list[FileChunk] = []

    # 1. Whole-program chunk (for global context)
    copy_refs = _COPY_RE.findall(source)
    call_refs = _CALL_RE.findall(source)
    select_pairs = _SELECT_RE.findall(source)  # [(logical_name, ddname), ...]
    fd_names = _FD_RE.findall(source)

    chunks.append(FileChunk(
        file_path=file_path,
        language="cobol",
        chunk_type="program",
        chunk_name=program_id,
        content=source,
        metadata={
            "program_id": program_id,
            "copy_refs": copy_refs,
            "call_refs": call_refs,
            "file_select_map": dict(select_pairs),
            "fd_names": fd_names,
        },
    ))

    # 2. Paragraph-level chunks from PROCEDURE DIVISION
    paragraphs = _split_into_paragraphs(source)
    lines = source.splitlines()
    for para_name, start, end in paragraphs:
        para_content = "\n".join(lines[start : end + 1])
        para_calls = _CALL_RE.findall(para_content)
        chunks.append(FileChunk(
            file_path=file_path,
            language="cobol",
            chunk_type="paragraph",
            chunk_name=f"{program_id}::{para_name}",
            content=para_content,
            metadata={
                "program_id": program_id,
                "paragraph": para_name,
                "call_refs": para_calls,
            },
        ))

    return chunks


def chunk_copybook(file_path: str) -> list[FileChunk]:
    """Parse a COBOL copybook (.cpy) and return a single chunk."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    name = Path(file_path).stem.upper()
    return [FileChunk(
        file_path=file_path,
        language="cobol",
        chunk_type="copybook",
        chunk_name=name,
        content=source,
        metadata={"copybook_name": name},
    )]


def chunk_jcl_file(file_path: str) -> list[FileChunk]:
    """
    Parse a JCL file and extract DD statement → physical dataset mappings.
    Returns one chunk per JCL step plus a whole-file summary chunk.
    """
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()

    # DD name → physical dataset name
    dd_map: dict[str, str] = {}
    current_step: str | None = None
    steps: dict[str, list[str]] = {}

    for line in lines:
        if line.startswith("//*") or not line.startswith("//"):
            continue
        # EXEC statement: //STEPxxx EXEC PGM=...
        exec_m = re.match(r"^//(\w+)\s+EXEC\s+PGM=(\w+)", line)
        if exec_m:
            current_step = exec_m.group(1)
            steps[current_step] = []
            continue
        # DD statement: //DDNAME DD DSN=...
        dd_m = re.match(r"^//(\w+)\s+DD\s+.*DSN=([^\s,]+)", line)
        if dd_m and current_step:
            ddname = dd_m.group(1)
            dsn = dd_m.group(2).strip()
            dd_map[ddname] = dsn
            steps[current_step].append(f"{ddname} -> {dsn}")

    job_name = Path(file_path).stem.upper()

    chunks: list[FileChunk] = []

    # Whole-file chunk
    chunks.append(FileChunk(
        file_path=file_path,
        language="jcl",
        chunk_type="job",
        chunk_name=job_name,
        content=source,
        metadata={"dd_map": dd_map, "steps": list(steps.keys())},
    ))

    # Per-step chunks — skip steps that have no DD→DSN mappings (e.g. steps
    # that only use SYSOUT=* or inline DD * statements) to avoid sending an
    # empty string to the embedding model, which rejects minLength: 1.
    for step_name, dd_lines in steps.items():
        if not dd_lines:
            continue
        chunks.append(FileChunk(
            file_path=file_path,
            language="jcl",
            chunk_type="step",
            chunk_name=f"{job_name}::{step_name}",
            content="\n".join(dd_lines),
            metadata={"job_name": job_name, "step_name": step_name},
        ))

    return chunks
