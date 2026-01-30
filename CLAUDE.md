# Sweatpants - Agent Instructions

## Project Overview

Sweatpants is a server-side automation engine for long-running tasks. It serves as the "work plane" counterpart to Homeboy (the "control plane").

**Role Division:**
- **Homeboy** (Rust, local): Developer interface, orchestration, remote control
- **Sweatpants** (Python, server): Automation execution, long-running jobs

## Architecture

```
sweatpants/
├── sweatpants/
│   ├── __init__.py         # Package exports (Module, proxied_request, get_browser)
│   ├── __main__.py         # CLI entry point
│   ├── cli.py              # Typer CLI commands
│   ├── config.py           # Pydantic settings
│   ├── engine/
│   │   ├── module_loader.py  # Module installation and loading
│   │   ├── job_scheduler.py  # Async job execution
│   │   └── state.py          # SQLite persistence
│   ├── api/
│   │   ├── main.py           # FastAPI app factory
│   │   ├── routes.py         # REST endpoints
│   │   └── scheduler.py      # Scheduler singleton
│   ├── proxy/
│   │   └── client.py         # Rotating proxy integration
│   ├── browser/
│   │   └── pool.py           # Playwright browser pool
│   └── sdk/
│       └── module.py         # Base Module class
└── examples/
    └── hello-world/          # Example module
```

## Commands

```bash
# Development
pip install -e .
playwright install chromium

# Run daemon
sweatpants serve

# Check status
sweatpants status

# Module management
sweatpants module list
sweatpants module install ./path/to/module
sweatpants module uninstall <module-id>

# Job management
sweatpants run <module-id> -i key=value
sweatpants stop <job-id>
sweatpants logs <job-id>
sweatpants logs <job-id> --follow
```

## Module Development

Modules are self-contained automation packages with:

1. **module.json** - Manifest with id, inputs, settings, capabilities
2. **main.py** - Entry point with Module subclass
3. **requirements.txt** - Optional dependencies

### Module SDK

```python
from sweatpants import Module, proxied_request, get_browser

class MyModule(Module):
    async def run(self, inputs, settings):
        # Log progress
        await self.log("Starting work...")

        # HTTP with rotating proxy
        response = await proxied_request("GET", "https://example.com")

        # Browser automation with proxy
        async with get_browser() as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")

        # Yield results incrementally
        yield {"data": "result"}

        # Save checkpoint for resume
        await self.save_checkpoint(progress=50)
```

## Key Patterns

### State Management
- SQLite for persistence (`sweatpants.db`)
- Jobs can resume from checkpoints after restart
- Results and logs stored per-job

### Proxy Integration
- Direct Bright Data proxy integration (no external service dependency)
- All HTTP requests and browser sessions route through proxy
- Service fails to start if proxy credentials not configured

### Browser Pool
- Playwright Chromium with pool management
- Automatic restart every N hours to prevent leaks
- Proxy configuration passthrough

### REST API
- FastAPI on port 8420 (configurable)
- WebSocket support for log streaming
- Internal auth via X-Internal-Auth header

## Environment Variables

All prefixed with `SWEATPANTS_`:

| Variable | Default | Description |
|----------|---------|-------------|
| DATA_DIR | /var/lib/sweatpants | Data directory |
| MODULES_DIR | /var/lib/sweatpants/modules | Installed modules |
| DB_PATH | /var/lib/sweatpants/sweatpants.db | SQLite database |
| API_HOST | 127.0.0.1 | API bind host |
| API_PORT | 8420 | API port |
| API_AUTH_TOKEN | (empty) | API authentication token |
| BRIGHTDATA_USERNAME | (required) | Bright Data proxy username |
| BRIGHTDATA_PASSWORD | (required) | Bright Data proxy password |
| BRIGHTDATA_HOST | brd.superproxy.io | Bright Data proxy host |
| BRIGHTDATA_PORT | 22225 | Bright Data proxy port |
| BROWSER_POOL_SIZE | 3 | Browser instances |
| BROWSER_RESTART_HOURS | 4 | Browser lifecycle |

## Related Repositories

| Repo | Purpose |
|------|---------|
| Extra-Chill/sweatpants | This repo - core engine |
| Extra-Chill/sweatpants-modules-private | Private automation modules |
