"""API routes for Sweatpants."""

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sweatpants.api.scheduler import get_scheduler
from sweatpants.engine.module_loader import ModuleLoader
from sweatpants.engine.state import StateManager

router = APIRouter()


class JobCreateRequest(BaseModel):
    """Request body for creating a job."""

    module_id: str
    inputs: dict[str, Any] = {}
    settings: dict[str, Any] = {}


class ModuleInstallRequest(BaseModel):
    """Request body for installing a module."""

    source_path: str


@router.get("/status")
async def get_status() -> dict:
    """Get engine status and running jobs."""
    scheduler = get_scheduler()
    return await scheduler.get_status()


@router.get("/modules")
async def list_modules() -> dict:
    """List installed modules."""
    loader = ModuleLoader()
    modules = await loader.list()
    return {"modules": modules}


@router.get("/modules/{module_id}")
async def get_module(module_id: str) -> dict:
    """Get module details."""
    loader = ModuleLoader()
    module = await loader.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


@router.post("/modules/install")
async def install_module(request: ModuleInstallRequest) -> dict:
    """Install a module from a directory."""
    loader = ModuleLoader()
    try:
        manifest = await loader.install(request.source_path)
        return {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/modules/{module_id}")
async def uninstall_module(module_id: str) -> dict:
    """Uninstall a module."""
    loader = ModuleLoader()
    success = await loader.uninstall(module_id)
    if not success:
        raise HTTPException(status_code=404, detail="Module not found")
    return {"status": "uninstalled", "module_id": module_id}


@router.post("/jobs")
async def create_job(request: JobCreateRequest) -> dict:
    """Start a new job."""
    scheduler = get_scheduler()
    try:
        job_id = await scheduler.start_job(
            module_id=request.module_id,
            inputs=request.inputs,
            settings=request.settings,
        )
        return {"id": job_id, "status": "pending"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs")
async def list_jobs(status: Optional[str] = None) -> dict:
    """List jobs, optionally filtered by status."""
    state = StateManager()
    jobs = await state.list_jobs(status=status)
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Get job details."""
    state = StateManager()
    job = await state.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/stop")
async def stop_job(job_id: str) -> dict:
    """Stop a running job."""
    scheduler = get_scheduler()
    success = await scheduler.stop_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or not running")
    return {"status": "stopped", "job_id": job_id}


@router.get("/jobs/{job_id}/logs")
async def get_logs(job_id: str, limit: int = 100) -> dict:
    """Get logs for a job."""
    state = StateManager()
    job = await state.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logs = await state.get_logs(job_id, limit=limit)
    return {"logs": logs}


@router.websocket("/jobs/{job_id}/logs/stream")
async def stream_logs(websocket: WebSocket, job_id: str) -> None:
    """Stream logs for a job via WebSocket."""
    await websocket.accept()

    state = StateManager()
    job = await state.get_job(job_id)
    if not job:
        await websocket.close(code=4004, reason="Job not found")
        return

    scheduler = get_scheduler()
    queue = scheduler.subscribe_logs(job["id"])

    try:
        while True:
            try:
                log_entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(log_entry)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        scheduler.unsubscribe_logs(job["id"], queue)


@router.get("/jobs/{job_id}/results")
async def get_results(job_id: str, limit: int = 1000) -> dict:
    """Get results for a job."""
    state = StateManager()
    job = await state.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    results = await state.get_results(job_id, limit=limit)
    count = await state.get_result_count(job_id)
    return {"results": results, "total": count}
