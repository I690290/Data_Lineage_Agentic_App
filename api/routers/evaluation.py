"""Evaluation report endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

# In-memory review decisions (persisted only for server lifetime)
_review_decisions: dict[str, dict[str, Any]] = {}


@router.get("/report")
async def get_latest_report() -> dict[str, Any]:
    """Return the most recent evaluation report, or an empty-shaped stub when none exists."""
    reports_dir = Path("evaluation/reports")
    if reports_dir.exists():
        reports = sorted(reports_dir.glob("eval_*.json"), reverse=True)
        if reports:
            try:
                with open(reports[0], encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))

    # Return a well-formed stub so the React EvaluationReport type doesn't crash
    return {
        "run_id": "not-run",
        "timestamp": "",
        "level1": None,
        "level2": None,
        "level3": None,
        "human_review_queue": [],
        "_message": "No evaluation report found. Run: make eval",
    }


@router.get("/human-review")
async def get_human_review_queue() -> list[dict[str, Any]]:
    """Return assertions in the human review queue as a flat array."""
    review_file = Path("output/human_review.json")
    if not review_file.exists():
        return []
    try:
        with open(review_file, encoding="utf-8") as f:
            items: list[dict[str, Any]] = json.load(f)
        # Merge any in-session review decisions
        for item in items:
            if item.get("id") in _review_decisions:
                item["status"] = _review_decisions[item["id"]]["decision"]
        return items
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/human-review/{item_id}")
async def submit_review(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Record a human review decision (approved / rejected) for a queued assertion."""
    decision = payload.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")
    _review_decisions[item_id] = {
        "item_id": item_id,
        "decision": decision,
        "notes": payload.get("notes", ""),
    }
    return {"ok": True, "item_id": item_id, "decision": decision}

