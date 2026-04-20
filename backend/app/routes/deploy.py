import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.terraform_service import (
    create_workspace,
    get_job,
    get_state,
    list_jobs,
    run_deploy,
    run_destroy,
)

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/deploy", tags=["deploy"])

_tasks: dict[str, asyncio.Task[None]] = {}


class DeployRequest(BaseModel):
    terraform_code: str | None = Field(default=None, min_length=1)
    use_local_main_tf: bool = False


def _read_local_main_tf() -> str:
    candidates = [
        Path("main.tf"),
        Path("backend/main.tf"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise HTTPException(
        status_code=404,
        detail="No local main.tf found. Provide terraform_code or create main.tf at project root.",
    )


async def _consume_deploy(job_id: str) -> None:
    try:
        async for _ in run_deploy(job_id):
            pass
    except Exception:
        logger.exception("[DEPLOY] Background deploy crashed for job=%s", job_id)


async def _consume_destroy(job_id: str) -> None:
    try:
        async for _ in run_destroy(job_id):
            pass
    except Exception:
        logger.exception("[DEPLOY] Background destroy crashed for job=%s", job_id)


@router.post("")
async def deploy_in_background(payload: DeployRequest) -> dict[str, Any]:
    terraform_code = payload.terraform_code

    if not terraform_code and payload.use_local_main_tf:
        terraform_code = _read_local_main_tf()

    if not terraform_code:
        raise HTTPException(
            status_code=400,
            detail="Provide terraform_code or set use_local_main_tf=true.",
        )

    job_id = create_workspace(terraform_code)
    task = asyncio.create_task(_consume_deploy(job_id))
    _tasks[job_id] = task

    logger.info("[DEPLOY] Started background deploy job=%s", job_id)
    return {"job_id": job_id, "status": "started"}


@router.post("/{job_id}/destroy")
async def destroy_in_background(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job {job_id}")

    task = asyncio.create_task(_consume_destroy(job_id))
    _tasks[job_id] = task

    logger.info("[DEPLOY] Started background destroy job=%s", job_id)
    return {"job_id": job_id, "status": "destroy_started"}


@router.get("/jobs")
async def get_jobs() -> dict[str, Any]:
    return {"jobs": list_jobs()}


@router.get("/{job_id}")
async def get_job_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job {job_id}")

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "error": job.get("error"),
        "outputs": job.get("outputs"),
    }


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: str, tail: int = 500) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job {job_id}")

    if tail <= 0:
        tail = 500

    logs = job.get("logs", [])
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "logs": logs[-tail:],
    }


@router.get("/{job_id}/state")
async def get_job_state(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job {job_id}")

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "state": get_state(job_id),
    }
