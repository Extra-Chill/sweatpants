# Module Class

Base class for all Sweatpants automation modules.

## Import

```python
from sweatpants import Module
```

## Overview

Modules must subclass `Module` and implement the `run()` method as an async generator that yields results.

```python
from sweatpants import Module

class MyModule(Module):
    async def run(self, inputs, settings):
        for item in items:
            await self.log(f"Processing {item}")
            result = await self.process(item)
            yield result
```

## Properties

### job_id

```python
@property
def job_id(self) -> str
```

Get the current job ID.

### is_cancelled

```python
@property
def is_cancelled(self) -> bool
```

Check if the job has been cancelled. Use this to exit gracefully when the user stops a job.

```python
async def run(self, inputs, settings):
    for item in items:
        if self.is_cancelled:
            await self.log("Job cancelled, stopping...")
            return
        yield await self.process(item)
```

## Methods

### log

```python
async def log(self, message: str, level: str = "INFO") -> None
```

Log a message for this job. Logs are stored in the database and can be streamed via WebSocket.

**Parameters:**
- `message` — The log message
- `level` — Log level: `INFO`, `WARNING`, or `ERROR`

```python
await self.log("Starting processing...")
await self.log("Rate limited, retrying...", level="WARNING")
await self.log("Failed to connect", level="ERROR")
```

### save_checkpoint

```python
async def save_checkpoint(self, **data: Any) -> None
```

Save checkpoint data for resume capability. Call periodically to enable job recovery after daemon restart.

**Parameters:**
- `**data` — Key-value pairs to save as checkpoint

```python
await self.save_checkpoint(
    progress=50,
    last_page=3,
    processed_ids=["a", "b", "c"]
)
```

### get_checkpoint

```python
def get_checkpoint(self, key: str, default: Any = None) -> Any
```

Get a value from the checkpoint.

```python
last_page = self.get_checkpoint("last_page", default=1)
```

### restore_checkpoint

```python
def restore_checkpoint(self, checkpoint: Optional[dict[str, Any]]) -> None
```

Called automatically by the scheduler when resuming a job. Updates internal checkpoint state.

## Abstract Method

### run

```python
@abstractmethod
async def run(
    self,
    inputs: dict[str, Any],
    settings: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]
```

Execute the module's main task. Must be implemented as an async generator.

**Parameters:**
- `inputs` — User-provided inputs for this job
- `settings` — Module configuration settings

**Yields:**
- `dict` — Result data to be stored

```python
async def run(self, inputs, settings):
    query = inputs["query"]
    api_key = settings.get("api_key")
    
    results = await self.fetch_results(query, api_key)
    
    for result in results:
        yield {"data": result}
```
