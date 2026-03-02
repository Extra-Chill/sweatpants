# Sweatpants

Lazy man's automation engine. Drop in a module, run a job, get results.

Sweatpants is a server-side Python engine for repeatable, long-running automation tasks. It has a modular architecture — you write small, focused modules as async generators, install them, and run them as jobs. The engine handles persistence, logging, checkpointing, resume, and real-time log streaming out of the box.

## How It Works

```
CLI / REST API
      │
      ▼
  JobScheduler ──► Module (async generator)
      │                  │
      │              yield results
      │                  │
  StateManager ◄─────────┘
   (SQLite)
```

1. You write a **module** — a Python class with an async `run()` method that yields results
2. You **install** it (from a directory or git repo)
3. You **run** it as a job via CLI or REST API
4. The engine persists results, streams logs, and handles cancellation/resume

## Quick Start

```bash
pip install -e .
playwright install chromium  # only if your modules use browser automation
```

```bash
# Start the daemon
sweatpants serve

# Install the example module
sweatpants module install ./examples/hello-world

# Run it
sweatpants run hello-world -i name="World"

# Watch it work
sweatpants logs <job-id> --follow

# Get results
sweatpants result <job-id>
```

## Writing a Module

A module is a directory with two files:

**module.json** — declares what the module is and what it needs:

```json
{
  "id": "hello-world",
  "name": "Hello World",
  "version": "1.0.0",
  "description": "A simple example module",
  "entrypoint": "main.py",
  "inputs": [
    {"id": "name", "type": "text", "required": true},
    {"id": "count", "type": "integer", "default": 3}
  ],
  "settings": [],
  "capabilities": []
}
```

**main.py** — a class that subclasses `Module` and implements `run()` as an async generator:

```python
import asyncio
from sweatpants import Module

class HelloWorld(Module):
    async def run(self, inputs, settings):
        name = inputs["name"]
        count = inputs.get("count", 3)

        for i in range(count):
            if self.is_cancelled:
                return

            await self.log(f"Greeting {i + 1} of {count}")
            await asyncio.sleep(1)

            # Yield results incrementally — each one is persisted
            yield {"greeting": f"Hello, {name}!", "iteration": i + 1}

            # Checkpoint for resume after restart
            await self.save_checkpoint(completed=i + 1)

        await self.log("Done!")
```

That's it. Install with `sweatpants module install ./your-module` and run with `sweatpants run your-module`.

## Batteries Included

Modules can declare **capabilities** to use built-in infrastructure:

```python
from sweatpants import Module, proxied_request, get_browser

class ScraperModule(Module):
    async def run(self, inputs, settings):
        # HTTP requests through a rotating proxy
        response = await proxied_request("GET", "https://example.com/api")

        # Browser automation with Playwright (proxied, pooled)
        async with get_browser() as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
            content = await page.content()

        yield {"content": content}
```

- **Rotating proxy** — provider-agnostic HTTP proxy with sticky sessions and geo-targeting
- **Browser pool** — managed Playwright Chromium instances with automatic restart and proxy integration
- **Checkpointing** — save progress, resume interrupted jobs automatically on daemon restart
- **Log streaming** — real-time WebSocket log streaming for live monitoring

## CLI

```bash
sweatpants serve                          # Start the daemon
sweatpants status                         # Engine status and running jobs
sweatpants config                         # Show effective configuration

sweatpants run <module> -i key=value      # Start a job
sweatpants run <module> -d 2h             # Start with auto-stop after 2 hours
sweatpants stop <job-id>                  # Stop a running job
sweatpants logs <job-id>                  # View logs
sweatpants logs <job-id> --follow         # Stream logs in real-time
sweatpants result <job-id>                # Get results

sweatpants module list                    # List installed modules
sweatpants module install ./path          # Install from directory
sweatpants module install-git <url>       # Install from git repo
sweatpants module uninstall <id>          # Remove a module
sweatpants module sync                    # Bulk sync from modules.yaml
```

## REST API

The daemon exposes a full REST API on port 8420 for remote control:

```
GET  /status                - Engine status and running jobs
GET  /modules               - List installed modules
POST /modules/install       - Install from local path
POST /modules/install-git   - Install from git repo
POST /modules/sync          - Bulk sync from modules.yaml
POST /modules/reload        - Hot-reload modules without restart
GET  /jobs                  - List all jobs
POST /jobs                  - Start a job
GET  /jobs/<id>             - Job status
POST /jobs/<id>/stop        - Stop a job
GET  /jobs/<id>/logs        - Get logs
WS   /jobs/<id>/logs/stream - Stream logs via WebSocket
GET  /jobs/<id>/results     - Get results
POST /proxy-fetch           - Forward HTTP requests through proxy
POST /callbacks             - Receive orchestration callbacks
GET  /callbacks/<id>        - Get callback status
```

## Module Sources

For managing many modules across repos, create a `modules.yaml`:

```yaml
module_sources:
  - repo: https://github.com/your-org/your-modules
    modules: [module-a, module-b]
  - repo: https://github.com/your-org/more-modules
    modules: [module-c]
```

Then run `sweatpants module sync` to install/update all of them at once.

## Configuration

Environment variables (prefix `SWEATPANTS_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/var/lib/sweatpants` | Data directory |
| `MODULES_DIR` | `/var/lib/sweatpants/modules` | Installed modules |
| `DB_PATH` | `/var/lib/sweatpants/sweatpants.db` | SQLite database |
| `API_HOST` | `127.0.0.1` | API bind host |
| `API_PORT` | `8420` | API port |
| `API_AUTH_TOKEN` | *(unset)* | API authentication token |
| `PROXY_URL` | *(unset)* | Rotating proxy URL |
| `PROXY_ROTATION_URL` | *(unset)* | Sticky session URL pattern |
| `BROWSER_POOL_SIZE` | `3` | Concurrent browser instances |
| `BROWSER_RESTART_HOURS` | `4` | Browser restart interval |
| `LOG_LEVEL` | `INFO` | Log verbosity |

## Running as a Service

```ini
[Unit]
Description=Sweatpants Automation Engine
After=network.target

[Service]
Type=simple
User=sweatpants
WorkingDirectory=/opt/sweatpants
ExecStart=/opt/sweatpants/venv/bin/sweatpants serve
Restart=always
RestartSec=10
Environment=SWEATPANTS_DATA_DIR=/var/lib/sweatpants

[Install]
WantedBy=multi-user.target
```

## License

MIT
