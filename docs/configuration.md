# Configuration

Sweatpants is configured via environment variables with the `SWEATPANTS_` prefix.

## Environment Variables

### Directories

| Variable | Default | Description |
|----------|---------|-------------|
| `SWEATPANTS_DATA_DIR` | `/var/lib/sweatpants` | Data directory for all persistent storage |
| `SWEATPANTS_MODULES_DIR` | `/var/lib/sweatpants/modules` | Installed modules directory |
| `SWEATPANTS_DB_PATH` | `/var/lib/sweatpants/sweatpants.db` | SQLite database path |
| `SWEATPANTS_MODULES_CONFIG_PATH` | `/var/lib/sweatpants/modules.yaml` | Module sources configuration |

### API Server

| Variable | Default | Description |
|----------|---------|-------------|
| `SWEATPANTS_API_HOST` | `127.0.0.1` | API bind host |
| `SWEATPANTS_API_PORT` | `8420` | API port |
| `SWEATPANTS_API_AUTH_TOKEN` | (empty) | API authentication token |

### Proxy

| Variable | Default | Description |
|----------|---------|-------------|
| `SWEATPANTS_PROXY_URL` | (required) | Full proxy URL: `http://user:pass@host:port` |
| `SWEATPANTS_PROXY_ROTATION_URL` | (optional) | URL pattern for sticky sessions with `{session}` placeholder |

### Browser Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `SWEATPANTS_BROWSER_POOL_SIZE` | `3` | Number of browser instances |
| `SWEATPANTS_BROWSER_RESTART_HOURS` | `4` | Browser restart interval in hours |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `SWEATPANTS_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

## Module Sources Configuration

The `modules.yaml` file configures git repositories for `sweatpants module sync`:

```yaml
module_sources:
  - repo: https://github.com/org/sweatpants-modules
    modules:
      - image-generator
      - chart-generator
      - web-scraper
  
  - repo: https://github.com/org/private-modules
    modules:
      - custom-module
```

**Fields:**
- `repo` — Git repository URL (supports HTTPS and SSH)
- `modules` — List of subdirectory names containing modules. Omit for single-module repos.

## systemd Service

Example systemd unit file:

```ini
[Unit]
Description=Sweatpants Automation Engine
After=network.target

[Service]
Type=simple
User=sweatpants
WorkingDirectory=/opt/sweatpants
ExecStart=/opt/sweatpants/.venv/bin/sweatpants serve
Restart=always
RestartSec=10
Environment=SWEATPANTS_DATA_DIR=/var/lib/sweatpants
Environment=SWEATPANTS_PROXY_URL=http://user:pass@proxy.example.com:8080

[Install]
WantedBy=multi-user.target
```

## .env File

Environment variables can be loaded from a `.env` file in the working directory:

```bash
# /opt/sweatpants/.env
SWEATPANTS_DATA_DIR=/var/lib/sweatpants
SWEATPANTS_PROXY_URL=http://user:pass@proxy.example.com:8080
SWEATPANTS_BROWSER_POOL_SIZE=5
```
