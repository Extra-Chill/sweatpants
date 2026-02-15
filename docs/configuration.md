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

Sweatpants does **not** require root, but the default data paths (like `/var/lib/sweatpants`) are typically root-owned. If you're running the service as a non-root user, make sure you override `SWEATPANTS_DATA_DIR` (and related directory settings) to a writable location.

### Example (non-root install)

```ini
[Unit]
Description=Sweatpants Automation Engine
After=network.target

[Service]
Type=simple
User=openclaw
Environment=HOME=/home/openclaw
WorkingDirectory=/home/openclaw/services/sweatpants
ExecStart=/home/openclaw/services/sweatpants/.venv/bin/sweatpants serve
Restart=on-failure
RestartSec=5

# Non-root friendly data paths
Environment=SWEATPANTS_DATA_DIR=/home/openclaw/data
Environment=SWEATPANTS_MODULES_DIR=/home/openclaw/data/modules
Environment=SWEATPANTS_DB_PATH=/home/openclaw/data/sweatpants.db
Environment=SWEATPANTS_MODULES_CONFIG_PATH=/home/openclaw/data/modules.yaml

# Optional
# Environment=SWEATPANTS_PROXY_URL=http://user:pass@proxy.example.com:8080

[Install]
WantedBy=multi-user.target
```

### Example (root install)

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

By default, Sweatpants does not probe for a `.env` file relative to the current working directory.

To load environment variables from a `.env` file, set `SWEATPANTS_ENV_FILE` to an absolute path (for example via systemd `Environment=` or your shell).

**Tip:** If you're running as a non-root user, prefer storing the env file somewhere under that user's home directory (for example `/home/openclaw/.sweatpants.env`).

```bash
# /home/openclaw/.sweatpants.env
SWEATPANTS_DATA_DIR=/home/openclaw/data
SWEATPANTS_PROXY_URL=http://user:pass@proxy.example.com:8080
SWEATPANTS_BROWSER_POOL_SIZE=5

# then:
export SWEATPANTS_ENV_FILE=/home/openclaw/.sweatpants.env
```
