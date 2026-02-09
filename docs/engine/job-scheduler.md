# Job Scheduler

Async job execution engine that manages module runs, checkpoints, and lifecycle.

## JobContext

Context object passed to running modules providing logging and state management.

### Properties

#### job_id

```python
@property
def job_id(self) -> str
```

Current job identifier.

#### is_cancelled

```python
@property
def is_cancelled(self) -> bool
```

Whether the job has been cancelled via stop request or duration limit.

### Methods

#### cancel

```python
def cancel(self) -> None
```

Mark the job as cancelled. Sets `is_cancelled` to `True`.

#### log

```python
async def log(self, message: str, level: str = "INFO") -> None
```

Log a message for this job. Logs are persisted and broadcast to WebSocket subscribers.

#### save_result

```python
async def save_result(self, data: dict[str, Any]) -> None
```

Save a result from this job to the database.

#### save_checkpoint

```python
async def save_checkpoint(self, checkpoint: dict[str, Any]) -> None
```

Save checkpoint state for resume capability after restart.

## JobScheduler

Main scheduler class managing job execution.

### Properties

#### uptime

```python
@property
def uptime(self) -> str
```

Human-readable uptime string (e.g., "2h 15m").

### Methods

#### start_job

```python
async def start_job(
    self,
    module_id: str,
    inputs: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
    checkpoint: Optional[dict[str, Any]] = None,
    max_duration: Optional[str] = None,
) -> str
```

Start a new job.

**Parameters:**
- `module_id` — Module to run
- `inputs` — Input parameters
- `settings` — Module settings
- `checkpoint` — Checkpoint to resume from
- `max_duration` — Duration limit (e.g., `1h`, `24h`, `7d`)

**Returns:** Job ID

#### resume_job

```python
async def resume_job(
    self,
    job_id: str,
    module_id: str,
    inputs: dict[str, Any],
    settings: dict[str, Any],
    checkpoint: Optional[dict[str, Any]],
    max_duration: Optional[str] = None,
) -> None
```

Resume a previously running job from its last checkpoint.

#### stop_job

```python
async def stop_job(self, job_id: str) -> bool
```

Stop a running job. Returns `True` if job was found and stopped.

#### get_status

```python
async def get_status(self) -> dict
```

Get scheduler status including uptime, module count, and running jobs.

#### subscribe_logs

```python
def subscribe_logs(self, job_id: str) -> asyncio.Queue
```

Subscribe to real-time log updates for a job.

#### unsubscribe_logs

```python
def unsubscribe_logs(self, job_id: str, queue: asyncio.Queue) -> None
```

Unsubscribe from log updates.

#### resume_interrupted_jobs

```python
async def resume_interrupted_jobs(self) -> int
```

Resume jobs that were interrupted by daemon restart. Called on startup.

**Returns:** Number of jobs resumed.

## Job Lifecycle

1. **pending** — Job created, not yet started
2. **running** — Job executing
3. **completed** — Job finished successfully
4. **failed** — Job encountered an error
5. **stopped** — Job cancelled by user or duration limit

## Duration Watchdog

When `max_duration` is set, a watchdog task monitors the job:

1. Waits for the specified duration
2. Logs "Duration limit reached"
3. Cancels the job context
4. Job transitions to `stopped` status
