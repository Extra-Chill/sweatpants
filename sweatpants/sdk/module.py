"""Base module class for Sweatpants automation modules."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING

from sweatpants.sdk.callback import send_signed_callback as _send_signed_callback

if TYPE_CHECKING:
    from sweatpants.engine.job_scheduler import JobContext


class Module(ABC):
    """Base class for all Sweatpants automation modules.

    Modules must subclass this and implement the run() method as an async generator.

    Example:
        class MyModule(Module):
            async def run(self, inputs, settings):
                for item in items:
                    await self.log(f"Processing {item}")
                    result = await self.process(item)
                    yield result
    """

    def __init__(self, context: "JobContext") -> None:
        self._context = context
        self._checkpoint: dict[str, Any] = {}

    @property
    def job_id(self) -> str:
        """Get the current job ID."""
        return self._context.job_id

    @property
    def is_cancelled(self) -> bool:
        """Check if the job has been cancelled."""
        return self._context.is_cancelled

    async def log(self, message: str, level: str = "INFO") -> None:
        """Log a message for this job.

        Args:
            message: The log message
            level: Log level (INFO, WARNING, ERROR)
        """
        await self._context.log(message, level)

    async def save_checkpoint(self, **data: Any) -> None:
        """Save checkpoint data for resume capability.

        Call this periodically to save progress that can be resumed after restart.

        Args:
            **data: Key-value pairs to save as checkpoint
        """
        self._checkpoint.update(data)
        await self._context.save_checkpoint(self._checkpoint)

    def get_checkpoint(self, key: str, default: Any = None) -> Any:
        """Get a value from the checkpoint.

        Args:
            key: The checkpoint key
            default: Default value if key not found

        Returns:
            The checkpoint value or default
        """
        return self._checkpoint.get(key, default)

    def restore_checkpoint(self, checkpoint: Optional[dict[str, Any]]) -> None:
        """Restore checkpoint data after restart.

        Called automatically by the scheduler when resuming a job.

        Args:
            checkpoint: Previously saved checkpoint data
        """
        if checkpoint:
            self._checkpoint = checkpoint

    async def send_signed_callback(
        self,
        url: str,
        payload: dict[str, Any],
        secret: Optional[str],
        *,
        issuer: str = "sweatpants",
        user_id: Optional[int] = None,
    ) -> bool:
        """POST a completion payload to an external receiver with a signed token.

        Thin wrapper over the core SDK primitive
        (:func:`sweatpants.sdk.callback.send_signed_callback`) that wires in
        this job's logger and job_id automatically. When ``secret`` is set the
        request carries an ``Authorization: Bearer <token>`` header whose
        HMAC-SHA256 format round-trips with sweatpants core's
        ``_verify_signed_token`` and the WordPress
        ``wp_native_auth_verify_external_token`` verifier.

        The job_id is injected into the body under ``job_id`` (without
        overwriting an existing key) so receivers can correlate, and is also
        used as the token ``jti`` claim for trace.

        Best-effort: delivery failures are logged but NEVER propagated to the
        job result.

        Args:
            url: HTTP(S) endpoint to POST to.
            payload: JSON-serializable body.
            secret: Shared HMAC secret. ``None``/empty disables signing.
            issuer: ``iss`` claim in the signed token.
            user_id: ``sub`` claim — the user the callback represents.

        Returns:
            ``True`` iff the receiver returned a 2xx status.
        """
        job_id = getattr(self, "job_id", None)
        body = dict(payload)
        if job_id is not None and "job_id" not in body:
            body["job_id"] = job_id

        return await _send_signed_callback(
            url,
            body,
            secret,
            issuer=issuer,
            user_id=user_id,
            job_id=str(job_id) if job_id is not None else None,
            log=self.log,
        )

    @abstractmethod
    async def run(
        self,
        inputs: dict[str, Any],
        settings: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute the module's main task.

        This must be implemented as an async generator that yields results.

        Args:
            inputs: User-provided inputs for this job
            settings: Module configuration settings

        Yields:
            dict: Result data to be stored
        """
        yield {}
