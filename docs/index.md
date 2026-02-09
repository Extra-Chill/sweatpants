# Sweatpants Documentation

Server-side automation engine for long-running tasks.

## Overview

Sweatpants is the work plane counterpart to Homeboy. While Homeboy (Rust, local) handles orchestration and developer interface, Sweatpants (Python, server) executes automation tasks.

## Architecture

```
sweatpants/
├── api/          # FastAPI REST server
├── browser/      # Playwright browser pool
├── engine/       # Job scheduler and module loader
├── proxy/        # HTTP client with rotating proxy
└── sdk/          # Module development base class
```

## Quick Start

```bash
# Install
pip install -e .
playwright install chromium

# Start daemon
sweatpants serve

# Check status
sweatpants status
```

## Documentation

### CLI
- [CLI Commands](cli.md) — Command-line interface reference

### API
- [REST API](api.md) — HTTP endpoints and WebSocket streaming

### Configuration
- [Configuration](configuration.md) — Environment variables and settings

### Module Development (SDK)
- [Module Class](sdk/module.md) — Base class for automation modules
- [Module Manifest](sdk/manifest.md) — module.json schema
- [Proxy Client](sdk/proxy.md) — HTTP requests through rotating proxy
- [Browser Pool](sdk/browser.md) — Playwright browser automation

### Engine Internals
- [Job Scheduler](engine/job-scheduler.md) — Async job execution
- [Module Loader](engine/module-loader.md) — Module installation and loading

## Package Exports

The main package exports three items:

```python
from sweatpants import Module, proxied_request, get_browser
```

- `Module` — Base class for automation modules
- `proxied_request` — Async HTTP client with proxy support
- `get_browser` — Playwright browser context manager
