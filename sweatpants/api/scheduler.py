"""Scheduler singleton for API access."""

from sweatpants.engine.job_scheduler import JobScheduler

_scheduler: JobScheduler | None = None


def get_scheduler() -> JobScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler()
    return _scheduler
