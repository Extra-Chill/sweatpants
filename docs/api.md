# REST API

FastAPI REST API exposed by the Sweatpants daemon on port 8420.

## Status

### GET /status

Get engine status and running jobs.

**Response:**
```json
{
  "status": "running",
  "uptime": "2h 15m",
  "module_count": 5,
  "jobs": [
    {
      "id": "abc123...",
      "module": "image-generator",
      "status": "running",
      "started_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

## Modules

### GET /modules

List installed modules.

**Response:**
```json
{
  "modules": [
    {
      "id": "image-generator",
      "name": "Image Generator",
      "version": "1.0.0",
      "capabilities": ["browser"]
    }
  ]
}
```

### GET /modules/{module_id}

Get module details.

**Response:** Full module manifest including inputs, settings, and capabilities.

### POST /modules/install

Install a module from a local directory.

**Request:**
```json
{
  "source_path": "/path/to/module"
}
```

**Response:**
```json
{
  "id": "my-module",
  "name": "My Module",
  "version": "1.0.0"
}
```

### POST /modules/install-git

Install a module from a git repository.

**Request:**
```json
{
  "repo_url": "https://github.com/org/my-module",
  "module_name": "optional-subdirectory"
}
```

### DELETE /modules/{module_id}

Uninstall a module.

### POST /modules/sync

Sync modules from configured sources in `modules.yaml`.

**Response:**
```json
{
  "installed": [
    {"id": "module-1", "name": "Module 1", "version": "1.0.0", "source": "https://..."}
  ],
  "failed": [],
  "skipped": []
}
```

## Jobs

### GET /jobs

List jobs, optionally filtered by status.

**Query Parameters:**
- `status` — Filter by job status (`pending`, `running`, `completed`, `failed`, `stopped`)

### POST /jobs

Start a new job.

**Request:**
```json
{
  "module_id": "image-generator",
  "inputs": {"prompt": "sunset"},
  "settings": {},
  "max_duration": "1h"
}
```

**Response:**
```json
{
  "id": "job-uuid-here",
  "status": "pending"
}
```

### GET /jobs/{job_id}

Get job details.

### POST /jobs/{job_id}/stop

Stop a running job.

### GET /jobs/{job_id}/logs

Get logs for a job.

**Query Parameters:**
- `limit` — Maximum number of log entries (default: 100)

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2024-01-15T10:30:05Z",
      "level": "INFO",
      "message": "Starting job..."
    }
  ]
}
```

### WebSocket /jobs/{job_id}/logs/stream

Stream logs for a job in real-time.

Sends JSON log entries as they occur. Sends `{"type": "ping"}` every 30 seconds as keepalive.

### GET /jobs/{job_id}/results

Get results for a job.

**Query Parameters:**
- `limit` — Maximum number of results (default: 1000)

**Response:**
```json
{
  "results": [
    {"data": {"url": "https://..."}}
  ],
  "total": 15
}
```

## Proxy

### POST /proxy-fetch

Forward HTTP request through the configured proxy.

**Request:**
```json
{
  "method": "GET",
  "url": "https://example.com/api",
  "headers": {},
  "body": null,
  "browser_mode": false,
  "timeout": 60,
  "session_id": null,
  "geo": null
}
```

**Response:**
```json
{
  "success": true,
  "content": "...",
  "status_code": 200,
  "headers": {}
}
```

## Uploads

For headless-compute pipelines where the client doesn't want to keep the
raw input artifact (e.g. a browser uploading audio for transcription, where
only the resulting transcript is kept). Clients POST the file directly to
the daemon, get back a job-scoped local path, and pass that path as a
module input when creating the job.

### POST /uploads

Accept a multipart file upload, store it under a job-scoped tempdir.

**Request:** `multipart/form-data` with a `file` field.

```bash
curl -X POST https://your-host/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/recording.m4a"
```

**Response:**
```json
{
  "upload_id": "8f2c1e9a4b7d4e5fa6b8c9d0e1f2a3b4",
  "path": "/var/lib/sweatpants/uploads/8f2c.../recording.m4a",
  "filename": "recording.m4a",
  "size_bytes": 1245789,
  "mime_type": "audio/mp4",
  "created_at": 1720000000
}
```

The `path` value can be passed directly as a module input (e.g.
`audio-transcription`'s `audio_path`).

**Limits:**
- Max size: `SWEATPANTS_UPLOADS_MAX_BYTES` (default 500 MB)
- Files are written to disk in 1 MB chunks; oversized uploads return
  HTTP 413 mid-stream once the cap is exceeded
- Unclaimed uploads may be garbage-collected after `SWEATPANTS_UPLOADS_TTL_HOURS`
  (default 24h)

### GET /uploads/{upload_id}

Get metadata for an uploaded file. Does **not** stream the file content
(modules consume it via direct filesystem read using the returned `path`).

**Response:**
```json
{
  "upload_id": "8f2c1e9a4b7d4e5fa6b8c9d0e1f2a3b4",
  "path": "/var/lib/sweatpants/uploads/8f2c.../recording.m4a",
  "filename": "recording.m4a",
  "size_bytes": 1245789,
  "created_at": 1720000000
}
```

### DELETE /uploads/{upload_id}

Delete an uploaded file and its containing directory. Idempotent —
calling on a missing upload still returns `{"status":"deleted"}`.
