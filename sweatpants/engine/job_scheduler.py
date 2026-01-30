"""Async job scheduler for running module tasks."""

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sweatpants.engine.module_loader import ModuleLoader
from sweatpants.engine.state import StateManager
from sweatpants.utils import parse_duration


class JobContext:
    """Context passed to running jobs for logging and state management."""

    def __init__(
        self,
        job_id: str,
        state: StateManager,
        log_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> None:
        self.job_id = job_id
        self._state = state
        self._log_callback = log_callback
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    async def log(self, message: str, level: str = "INFO") -> None:
        """Log a message for this job."""
        await self._state.add_log(self.job_id, level, message)
        if self._log_callback:
            self._log_callback(self.job_id, level, message)

    async def save_result(self, data: dict[str, Any]) -> None:
        """Save a result from this job."""
        await self._state.add_result(self.job_id, data)

    async def save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Save checkpoint state for resume capability."""
        await self._state.update_job_status(
            self.job_id, "running", checkpoint=checkpoint
        )


class JobScheduler:
    """Manages async job execution."""

    def __init__(self) -> None:
        self.state = StateManager()
        self.module_loader = ModuleLoader()
        self._running_jobs: dict[str, asyncio.Task] = {}
        self._job_contexts: dict[str, JobContext] = {}
        self._log_subscribers: dict[str, list[asyncio.Queue]] = {}
        self._watchdogs: dict[str, asyncio.Task] = {}
        self._started_at: datetime = datetime.now(timezone.utc)

    @property
    def uptime(self) -> str:
        """Get human-readable uptime."""
        delta = datetime.now(timezone.utc) - self._started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def _broadcast_log(self, job_id: str, level: str, message: str) -> None:
        """Broadcast log to subscribers."""
        if job_id in self._log_subscribers:
            log_entry = {
                "level": level,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for queue in self._log_subscribers[job_id]:
                try:
                    queue.put_nowait(log_entry)
                except asyncio.QueueFull:
                    pass

    def subscribe_logs(self, job_id: str) -> asyncio.Queue:
        """Subscribe to log updates for a job."""
        if job_id not in self._log_subscribers:
            self._log_subscribers[job_id] = []
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._log_subscribers[job_id].append(queue)
        return queue

    def unsubscribe_logs(self, job_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from log updates."""
        if job_id in self._log_subscribers:
            try:
                self._log_subscribers[job_id].remove(queue)
            except ValueError:
                pass

    async def start_job(
        self,
        module_id: str,
        inputs: dict[str, Any],
        settings: Optional[dict[str, Any]] = None,
        checkpoint: Optional[dict[str, Any]] = None,
        max_duration: Optional[str] = None,
    ) -> str:
        """Start a new job.

        Args:
            module_id: The module to run
            inputs: Input parameters for the module
            settings: Optional module settings
            checkpoint: Optional checkpoint to resume from
            max_duration: Optional duration limit (e.g., '1h', '24h', '7d')
        """
        module_info = await self.module_loader.get(module_id)
        if not module_info:
            raise ValueError(f"Module not found: {module_id}")

        job_id = await self.state.create_job(
            module_id=module_id,
            inputs=inputs,
            settings=settings or {},
        )

        context = JobContext(
            job_id=job_id,
            state=self.state,
            log_callback=self._broadcast_log,
        )
        self._job_contexts[job_id] = context

        task = asyncio.create_task(
            self._run_job(job_id, module_id, inputs, settings or {}, checkpoint, context)
        )
        self._running_jobs[job_id] = task

        if max_duration:
            timeout_seconds = parse_duration(max_duration)
            watchdog = asyncio.create_task(
                self._duration_watchdog(job_id, context, timeout_seconds, max_duration)
            )
            self._watchdogs[job_id] = watchdog

        return job_id

    async def resume_job(
        self,
        job_id: str,
        module_id: str,
        inputs: dict[str, Any],
        settings: dict[str, Any],
        checkpoint: Optional[dict[str, Any]],
        max_duration: Optional[str] = None,
    ) -> None:
        """Resume a previously running job."""
        context = JobContext(
            job_id=job_id,
            state=self.state,
            log_callback=self._broadcast_log,
        )
        self._job_contexts[job_id] = context

        task = asyncio.create_task(
            self._run_job(job_id, module_id, inputs, settings, checkpoint, context)
        )
        self._running_jobs[job_id] = task

        if max_duration:
            timeout_seconds = parse_duration(max_duration)
            watchdog = asyncio.create_task(
                self._duration_watchdog(job_id, context, timeout_seconds, max_duration)
            )
            self._watchdogs[job_id] = watchdog

    async def _duration_watchdog(
        self,
        job_id: str,
        context: JobContext,
        timeout_seconds: int,
        duration_str: str,
    ) -> None:
        """Cancel job after duration limit reached."""
        try:
            await asyncio.sleep(timeout_seconds)
            await context.log(f"Duration limit reached ({duration_str}) - stopping job")
            context.cancel()
        except asyncio.CancelledError:
            pass

    async def _run_job(
        self,
        job_id: str,
        module_id: str,
        inputs: dict[str, Any],
        settings: dict[str, Any],
        checkpoint: Optional[dict[str, Any]],
        context: JobContext,
    ) -> None:
        """Execute a job."""
        try:
            await self.state.update_job_status(job_id, "running")
            await context.log(f"Starting job with module: {module_id}")

            module_class = await self.module_loader.load_class(module_id)
            module_instance = module_class(context)

            if checkpoint:
                await context.log(f"Resuming from checkpoint")
                module_instance.restore_checkpoint(checkpoint)

            async for result in module_instance.run(inputs, settings):
                if context.is_cancelled:
                    await context.log("Job cancelled")
                    await self.state.update_job_status(job_id, "stopped")
                    return

                await context.save_result(result)

            await context.log("Job completed successfully")
            await self.state.update_job_status(job_id, "completed")

        except asyncio.CancelledError:
            await context.log("Job cancelled")
            await self.state.update_job_status(job_id, "stopped")
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()
            await context.log(f"Job failed: {error_msg}\n{tb}", level="ERROR")
            await self.state.update_job_status(job_id, "failed", error=error_msg)
        finally:
            self._cleanup_job(job_id)

    def _cleanup_job(self, job_id: str) -> None:
        """Clean up after job completion."""
        if job_id in self._running_jobs:
            del self._running_jobs[job_id]
        if job_id in self._job_contexts:
            del self._job_contexts[job_id]
        if job_id in self._watchdogs:
            self._watchdogs[job_id].cancel()
            del self._watchdogs[job_id]

    async def stop_job(self, job_id: str) -> bool:
        """Stop a running job."""
        job = await self.state.get_job(job_id)
        if not job:
            return False

        full_job_id = job["id"]

        if full_job_id in self._job_contexts:
            self._job_contexts[full_job_id].cancel()

        if full_job_id in self._running_jobs:
            self._running_jobs[full_job_id].cancel()
            try:
                await self._running_jobs[full_job_id]
            except asyncio.CancelledError:
                pass
            return True

        return False

    async def get_status(self) -> dict:
        """Get scheduler status."""
        modules = await self.module_loader.list()
        running_jobs = []

        for job_id in self._running_jobs:
            job = await self.state.get_job(job_id)
            if job:
                running_jobs.append({
                    "id": job["id"],
                    "module": job["module_id"],
                    "status": job["status"],
                    "started_at": job["started_at"],
                })

        return {
            "status": "running",
            "uptime": self.uptime,
            "module_count": len(modules),
            "jobs": running_jobs,
        }

    async def resume_interrupted_jobs(self) -> int:
        """Resume jobs that were interrupted by a restart."""
        jobs = await self.state.get_resumable_jobs()
        count = 0

        for job in jobs:
            await self.resume_job(
                job_id=job["id"],
                module_id=job["module_id"],
                inputs=job["inputs"],
                settings=job["settings"],
                checkpoint=job["checkpoint"],
            )
            count += 1

        return count
