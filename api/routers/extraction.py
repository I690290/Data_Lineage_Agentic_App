"""Extraction trigger endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter()

_running_jobs: dict[str, str] = {}


class ExtractionRequest(BaseModel):
    repo_path: str


@router.post("/extract")
async def trigger_extraction(
    request: ExtractionRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Trigger lineage extraction for a repository path."""
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _running_jobs[job_id] = "running"

    def _run(job_id: str, repo_path: str) -> None:
        try:
            from agents.pipeline import run_pipeline
            run_pipeline(repo_path)
            _running_jobs[job_id] = "complete"
        except Exception as exc:
            _running_jobs[job_id] = f"failed: {exc}"

    background_tasks.add_task(_run, job_id, request.repo_path)
    return {"job_id": job_id, "status": "started", "repo_path": request.repo_path}


@router.get("/extract/{job_id}/status")
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Get the status of a running extraction job."""
    status = _running_jobs.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"job_id": job_id, "status": status}
