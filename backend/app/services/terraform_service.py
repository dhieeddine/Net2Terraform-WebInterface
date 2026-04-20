"""Terraform subprocess manager.

Handles workspace creation, terraform init/apply/destroy,
real-time log streaming (async generators), and tfstate parsing.
"""

import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from ..core.config import (
    AWS_ACCESS_KEY_ID,
    AWS_DEFAULT_REGION,
    AWS_SECRET_ACCESS_KEY,
    DEPLOYMENTS_DIR,
)

logger = logging.getLogger("uvicorn.error")

# In-memory job registry — maps job_id → metadata dict
_jobs: dict[str, dict[str, Any]] = {}


def _terraform_env() -> dict[str, str]:
    """Build environment dict for terraform subprocess."""
    import os

    env = os.environ.copy()
    if AWS_ACCESS_KEY_ID:
        env["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    if AWS_SECRET_ACCESS_KEY:
        env["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY
    if AWS_DEFAULT_REGION:
        env["AWS_DEFAULT_REGION"] = AWS_DEFAULT_REGION
    # Disable interactive prompts
    env["TF_INPUT"] = "0"
    # Use compact, machine-friendly output when possible
    env["TF_IN_AUTOMATION"] = "1"
    return env


def _check_terraform_installed() -> bool:
    """Return True if `terraform` is reachable on PATH."""
    return shutil.which("terraform") is not None


def create_workspace(terraform_code: str) -> str:
    """Write main.tf into a fresh per-job directory. Return job_id."""
    job_id = uuid.uuid4().hex[:12]
    workspace = DEPLOYMENTS_DIR / job_id
    workspace.mkdir(parents=True, exist_ok=True)

    tf_file = workspace / "main.tf"
    tf_file.write_text(terraform_code, encoding="utf-8")

    _jobs[job_id] = {
        "status": "created",
        "workspace": str(workspace),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "logs": [],
        "error": None,
        "outputs": None,
    }

    logger.info("[DEPLOY] Created workspace %s at %s", job_id, workspace)
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    """Return job metadata dict or None."""
    return _jobs.get(job_id)


def list_jobs() -> list[dict[str, Any]]:
    """Return summary of all jobs."""
    return [
        {"job_id": jid, "status": meta["status"], "created_at": meta["created_at"]}
        for jid, meta in _jobs.items()
    ]


async def _stream_process(
    cmd: list[str],
    cwd: Path,
    job_id: str,
    phase: str,
) -> AsyncGenerator[str, None]:
    """Run *cmd* as a subprocess and yield each output line as it arrives."""
    env = _terraform_env()

    yield f"[{phase}] Starting: {' '.join(cmd)}\n"
    logger.info("[DEPLOY:%s] %s → %s", job_id, phase, " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd),
        env=env,
    )

    assert process.stdout is not None
    while True:
        line_bytes = await process.stdout.readline()
        if not line_bytes:
            break
        line = line_bytes.decode("utf-8", errors="replace")
        _jobs[job_id]["logs"].append(line)
        yield line

    await process.wait()
    rc = process.returncode
    summary = f"[{phase}] Exited with code {rc}\n"
    _jobs[job_id]["logs"].append(summary)
    yield summary

    if rc != 0:
        raise RuntimeError(f"{phase} failed (exit {rc})")


async def run_deploy(job_id: str) -> AsyncGenerator[str, None]:
    """Run terraform init + apply and stream all output lines."""
    job = _jobs.get(job_id)
    if job is None:
        raise ValueError(f"Unknown job {job_id}")

    if not _check_terraform_installed():
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = "Terraform CLI not found on PATH"
        yield "[ERROR] Terraform CLI is not installed or not on PATH.\n"
        return

    workspace = Path(job["workspace"])
    _jobs[job_id]["status"] = "initializing"
    _jobs[job_id]["error"] = None

    # --- terraform init ---
    try:
        async for line in _stream_process(
            ["terraform", "init", "-no-color"],
            workspace,
            job_id,
            "INIT",
        ):
            yield line
    except RuntimeError as exc:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)
        yield f"[ERROR] {exc}\n"
        return

    # --- terraform apply ---
    _jobs[job_id]["status"] = "applying"
    yield "\n[APPLY] Running terraform apply -auto-approve ...\n"
    try:
        async for line in _stream_process(
            ["terraform", "apply", "-auto-approve", "-no-color"],
            workspace,
            job_id,
            "APPLY",
        ):
            yield line
    except RuntimeError as exc:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)
        yield f"[ERROR] {exc}\n"
        return

    # --- success ---
    _jobs[job_id]["status"] = "deployed"
    _jobs[job_id]["outputs"] = _parse_outputs(workspace)
    yield "\n[DONE] Infrastructure deployed successfully ✓\n"


async def run_destroy(job_id: str) -> AsyncGenerator[str, None]:
    """Run terraform destroy and stream output."""
    job = _jobs.get(job_id)
    if job is None:
        raise ValueError(f"Unknown job {job_id}")

    if not _check_terraform_installed():
        yield "[ERROR] Terraform CLI is not installed or not on PATH.\n"
        return

    workspace = Path(job["workspace"])
    _jobs[job_id]["status"] = "destroying"
    _jobs[job_id]["error"] = None

    try:
        async for line in _stream_process(
            ["terraform", "destroy", "-auto-approve", "-no-color"],
            workspace,
            job_id,
            "DESTROY",
        ):
            yield line
    except RuntimeError as exc:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)
        yield f"[ERROR] {exc}\n"
        return

    _jobs[job_id]["status"] = "destroyed"
    yield "\n[DONE] Infrastructure destroyed ✓\n"


def _parse_outputs(workspace: Path) -> dict[str, Any]:
    """Try to read terraform.tfstate and extract resource summaries."""
    state_path = workspace / "terraform.tfstate"
    if not state_path.exists():
        return {}

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        resources = []
        for res in state.get("resources", []):
            for inst in res.get("instances", []):
                attrs = inst.get("attributes", {})
                resources.append(
                    {
                        "type": res.get("type", "unknown"),
                        "name": res.get("name", "unknown"),
                        "id": attrs.get("id", ""),
                        "public_ip": attrs.get("public_ip", ""),
                        "private_ip": attrs.get("private_ip", ""),
                        "availability_zone": attrs.get("availability_zone", ""),
                        "state": attrs.get("instance_state", attrs.get("status", "")),
                    }
                )
        return {"resources": resources}
    except Exception as exc:
        logger.warning("[DEPLOY] Failed to parse tfstate: %s", exc)
        return {"parse_error": str(exc)}


def get_state(job_id: str) -> dict[str, Any]:
    """Return parsed tfstate resources for the given job."""
    job = _jobs.get(job_id)
    if job is None:
        raise ValueError(f"Unknown job {job_id}")
    workspace = Path(job["workspace"])
    return _parse_outputs(workspace)
