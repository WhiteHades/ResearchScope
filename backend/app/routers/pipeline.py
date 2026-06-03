from __future__ import annotations

import os
import httpx
from fastapi import APIRouter, Header, HTTPException

from app.schemas import PipelineTriggerOut

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_PIPELINE_SECRET = os.environ.get("PIPELINE_SECRET", "")
_GH_TOKEN        = os.environ.get("GITHUB_TOKEN", "")
_GH_REPO         = os.environ.get("GITHUB_REPO", "kishormorol/ResearchScope")
_GH_WORKFLOW     = os.environ.get("GITHUB_WORKFLOW", "pipeline.yml")


@router.post("/trigger", response_model=PipelineTriggerOut)
async def trigger_pipeline(x_pipeline_secret: str = Header(...)):
    if not _PIPELINE_SECRET or x_pipeline_secret != _PIPELINE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid pipeline secret")

    if not _GH_TOKEN:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN not configured")

    url = f"https://api.github.com/repos/{_GH_REPO}/actions/workflows/{_GH_WORKFLOW}/dispatches"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={"ref": "main"},
            headers={
                "Authorization": f"Bearer {_GH_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )

    if resp.status_code == 204:
        run_url = f"https://github.com/{_GH_REPO}/actions/workflows/{_GH_WORKFLOW}"
        return PipelineTriggerOut(status="triggered", message="Pipeline dispatched via GitHub Actions", workflow_run_url=run_url)

    raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code} {resp.text}")
