"""API routes for Sweatpants."""

import asyncio
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sweatpants.api.scheduler import get_scheduler
from sweatpants.config import get_settings
from sweatpants.engine.module_loader import ModuleLoader
from sweatpants.engine.state import StateManager
from sweatpants.proxy.client import proxied_request

router = APIRouter()


class JobCreateRequest(BaseModel):
    """Request body for creating a job."""

    module_id: str
    inputs: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    max_duration: Optional[str] = None


class ModuleInstallRequest(BaseModel):
    """Request body for installing a module."""

    source_path: str


class ModuleInstallGitRequest(BaseModel):
    """Request body for installing a module from git."""

    repo_url: str
    module_name: Optional[str] = None


class ProxyFetchRequest(BaseModel):
    """Request body for proxy fetch endpoint."""

    method: str = "GET"
    url: str
    headers: dict[str, str] = {}
    body: Optional[str] = None
    browser_mode: bool = False
    timeout: Optional[int] = None
    session_id: Optional[str] = None
    geo: Optional[str] = None


class ProxyFetchResponse(BaseModel):
    """Response body from proxy fetch endpoint."""

    success: bool
    content: str = ""
    status_code: int = 0
    headers: dict[str, str] = {}
    error: Optional[str] = None


class CallbackRequest(BaseModel):
    """Request body for receiving a callback."""

    callback_id: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    payload: dict[str, Any] = {}


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


@router.post("/modules/install-git")
async def install_module_git(request: ModuleInstallGitRequest) -> dict:
    """Install a module from a git repository."""
    loader = ModuleLoader()
    try:
        manifest = await loader.install_from_git(
            repo_url=request.repo_url,
            module_name=request.module_name,
        )
        return {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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


@router.post("/modules/sync")
async def sync_modules() -> dict:
    """Sync modules from configured module sources.

    Reads module_sources from modules.yaml config file, clones/pulls each repo,
    and installs the specified modules.

    Returns summary with installed, failed, and skipped modules.
    Raises 400 if no module_sources configured.
    """
    loader = ModuleLoader()
    try:
        result = await loader.sync_modules()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/modules/reload")
async def reload_modules() -> dict:
    """Reload all modules from disk without restarting.

    Clears the in-memory module cache and re-discovers modules
    from the modules directory. Use after updating module files
    on disk (via sync, manual edits, or PR merges).
    """
    loader = ModuleLoader()
    try:
        result = await loader.reload_all()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs")
async def create_job(request: JobCreateRequest) -> dict:
    """Start a new job."""
    scheduler = get_scheduler()
    try:
        job_id = await scheduler.start_job(
            module_id=request.module_id,
            inputs=request.inputs,
            settings=request.settings,
            max_duration=request.max_duration,
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


@router.post("/proxy-fetch", response_model=ProxyFetchResponse)
async def proxy_fetch(request: ProxyFetchRequest) -> ProxyFetchResponse:
    """Forward HTTP request through Bright Data proxy.

    Used by WordPress to proxy requests through the VPS.
    """
    try:
        response = await proxied_request(
            method=request.method.upper(),
            url=request.url,
            headers=request.headers if request.headers else None,
            data=request.body.encode() if request.body else None,
            timeout=float(request.timeout) if request.timeout else 60.0,
            browser_mode=request.browser_mode,
            session_id=request.session_id,
            geo=request.geo,
        )
        return ProxyFetchResponse(
            success=True,
            content=response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
    except Exception as e:
        return ProxyFetchResponse(
            success=False,
            error=str(e),
        )


@router.post("/callbacks")
async def receive_callback(request: CallbackRequest) -> dict:
    """Receive a callback from an external source.

    Used for orchestration - agents can POST results back after completing tasks.
    """
    state = StateManager()
    cb_id = await state.save_callback(
        callback_id=request.callback_id,
        source=request.source,
        status=request.status,
        payload=request.payload,
    )
    return {"id": cb_id, "received": True}


@router.get("/callbacks")
async def list_callbacks(
    source: Optional[str] = None,
    callback_id: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """List callbacks, optionally filtered by source or callback_id."""
    state = StateManager()
    callbacks = await state.list_callbacks(
        source=source,
        callback_id=callback_id,
        limit=limit,
    )
    return {"callbacks": callbacks}


@router.get("/callbacks/{cb_id}")
async def get_callback(cb_id: str) -> dict:
    """Get a specific callback by ID."""
    state = StateManager()
    callback = await state.get_callback(cb_id)
    if not callback:
        raise HTTPException(status_code=404, detail="Callback not found")
    return callback


@router.delete("/callbacks/{cb_id}")
async def delete_callback(cb_id: str) -> dict:
    """Delete a callback by ID."""
    state = StateManager()
    success = await state.delete_callback(cb_id)
    if not success:
        raise HTTPException(status_code=404, detail="Callback not found")
    return {"status": "deleted", "id": cb_id}


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------
#
# Headless-compute pattern: clients POST audio/video/data directly here, get
# back a job-scoped local path, then submit a job referencing that path. This
# avoids the round-trip of "upload to your own WP install, then have sweatpants
# fetch it back over HTTP" — useful when the client doesn't want to keep the
# raw file (e.g. a Studio plugin that only cares about the transcript output).
#
# Storage layout: <uploads_dir>/<upload_id>/<sanitized_filename>
# - upload_id is a UUID4 (job-scoped tempdir)
# - sanitized filename preserves the original extension for module heuristics
#   (audio-transcription module uses extension to pick ffmpeg conversion path)
#
# Lifecycle:
# - Created via POST /uploads
# - Read via GET /uploads/{id} (metadata only — file content fetched by modules
#   directly from the returned `path`)
# - Deleted via DELETE /uploads/{id} or by GC after `uploads_ttl_hours`
#   (GC implementation deferred to a future PR — the dir is small and self-
#   limiting at `uploads_max_bytes` per upload anyway)
#
# Auth: gated by the same nginx bearer-token layer as the rest of the API.
# No additional in-process auth — the daemon trusts that requests reaching it
# have already been authenticated by the reverse proxy.


_INVALID_FILENAME_CHARS = '/\\:\x00'


def _sanitize_filename(filename: str) -> str:
    """Strip path separators and control chars from an uploaded filename.

    Preserves the original extension. Falls back to "upload.bin" if the
    sanitized name is empty.
    """
    cleaned = "".join(c for c in (filename or "") if c not in _INVALID_FILENAME_CHARS).strip()
    cleaned = cleaned.lstrip(".")  # disallow leading-dot dotfiles
    return cleaned or "upload.bin"


@router.post("/uploads")
async def create_upload(file: UploadFile = File(...)) -> dict:
    """Accept a multipart file upload, store it under a job-scoped tempdir.

    Returns metadata the client can pass to POST /jobs as a local path input
    (e.g. audio-transcription's `audio_path`). The file is written to disk in
    chunks to bound memory usage; oversized uploads are rejected mid-stream
    once they exceed `uploads_max_bytes`.

    Response: { upload_id, path, filename, size_bytes, mime_type, created_at }
    """
    settings = get_settings()
    uploads_dir = settings.uploads_dir
    if uploads_dir is None:
        raise HTTPException(status_code=500, detail="uploads_dir is not configured")

    upload_id = uuid.uuid4().hex
    upload_dir = Path(uploads_dir) / upload_id
    try:
        upload_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # Vanishingly unlikely UUID collision — surface as 500.
        raise HTTPException(status_code=500, detail="upload_id collision")

    filename = _sanitize_filename(file.filename or "")
    target_path = upload_dir / filename

    max_bytes = settings.uploads_max_bytes
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1 MB

    try:
        with target_path.open("wb") as out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"upload exceeds max size of {max_bytes} bytes",
                    )
                out.write(chunk)
    except HTTPException:
        # Cleanup partial upload before re-raising.
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"upload failed: {exc}") from exc
    finally:
        await file.close()

    return {
        "upload_id": upload_id,
        "path": str(target_path),
        "filename": filename,
        "size_bytes": bytes_written,
        "mime_type": file.content_type or "application/octet-stream",
        "created_at": int(time.time()),
    }


def _resolve_upload_dir(upload_id: str) -> Path:
    """Resolve and validate an upload_id to its directory.

    Rejects path-traversal attempts and IDs that aren't valid UUIDs.
    Raises HTTPException(404) for missing uploads.
    """
    settings = get_settings()
    uploads_dir = settings.uploads_dir
    if uploads_dir is None:
        raise HTTPException(status_code=500, detail="uploads_dir is not configured")

    # Strict UUID4 hex format — eliminates path traversal and exotic IDs.
    try:
        uuid.UUID(hex=upload_id, version=4)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="invalid upload_id")

    upload_dir = Path(uploads_dir) / upload_id
    if not upload_dir.is_dir():
        raise HTTPException(status_code=404, detail="upload not found")

    return upload_dir


@router.get("/uploads/{upload_id}")
async def get_upload(upload_id: str) -> dict:
    """Get metadata for an uploaded file.

    Does NOT stream the file content — that's only consumed by modules via
    direct filesystem read using the `path` returned from POST /uploads.
    """
    upload_dir = _resolve_upload_dir(upload_id)

    files = [p for p in upload_dir.iterdir() if p.is_file()]
    if not files:
        raise HTTPException(status_code=404, detail="upload directory is empty")

    target = files[0]
    stat = target.stat()
    return {
        "upload_id": upload_id,
        "path": str(target),
        "filename": target.name,
        "size_bytes": stat.st_size,
        "created_at": int(stat.st_ctime),
    }


@router.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str) -> dict:
    """Delete an uploaded file and its containing directory.

    Idempotent — calling on a missing upload still returns success.
    """
    settings = get_settings()
    uploads_dir = settings.uploads_dir
    if uploads_dir is None:
        raise HTTPException(status_code=500, detail="uploads_dir is not configured")

    try:
        uuid.UUID(hex=upload_id, version=4)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="invalid upload_id")

    upload_dir = Path(uploads_dir) / upload_id
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)

    return {"status": "deleted", "upload_id": upload_id}
