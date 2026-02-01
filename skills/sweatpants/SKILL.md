---
name: sweatpants
description: Interact with Sweatpants automation engine. Use when running automation modules, checking job status, viewing logs, or managing the Sweatpants service. Sweatpants runs on port 8420 and handles long-running tasks like image generation, web scraping, and API orchestration.
---

# Sweatpants

Sweatpants is a server-side automation engine for long-running tasks. It runs as a systemd service and exposes a REST API.

## Quick Commands

```bash
# Service management
systemctl status sweatpants
systemctl restart sweatpants

# CLI (run as sweatpants user or use full path)
sweatpants status
sweatpants module list
sweatpants run <module-id> -i key=value
sweatpants logs <job-id> --follow
sweatpants stop <job-id>
```

## REST API (port 8420)

```bash
# Status
curl http://localhost:8420/status

# List modules
curl http://localhost:8420/modules

# Run a module
curl -X POST http://localhost:8420/jobs \
  -H "Content-Type: application/json" \
  -d '{"module_id": "hello-world", "inputs": {"name": "test"}}'

# Get job status
curl http://localhost:8420/jobs/<job-id>

# Stream logs (WebSocket)
wscat -c ws://localhost:8420/jobs/<job-id>/logs
```

## Key Paths

| Path | Purpose |
|------|---------|
| `/home/sweatpants/services/sweatpants/` | Sweatpants installation |
| `/var/lib/sweatpants/modules/` | Installed modules |
| `/var/lib/sweatpants/sweatpants.db` | SQLite database |
| `/home/sweatpants/.sweatpants-secrets` | Environment secrets |

## Module Installation

```bash
# Install from local path
sweatpants module install /path/to/module

# Install from git
sweatpants module install https://github.com/org/repo.git#subfolder

# Uninstall
sweatpants module uninstall <module-id>
```

## Common Patterns

### Run module and wait for result
```bash
JOB_ID=$(curl -s -X POST http://localhost:8420/jobs \
  -H "Content-Type: application/json" \
  -d '{"module_id": "my-module", "inputs": {"key": "value"}}' | jq -r '.job_id')

# Poll until complete
while true; do
  STATUS=$(curl -s http://localhost:8420/jobs/$JOB_ID | jq -r '.status')
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 2
done

# Get results
curl -s http://localhost:8420/jobs/$JOB_ID/results
```

### Check if module exists
```bash
curl -s http://localhost:8420/modules | jq -e ".[] | select(.id == \"$MODULE_ID\")" > /dev/null
```

## Environment Variables

Set in `/home/sweatpants/.sweatpants-secrets`:

| Variable | Description |
|----------|-------------|
| `SWEATPANTS_PROXY_URL` | Rotating proxy URL (required) |
| `SWEATPANTS_API_AUTH_TOKEN` | API authentication token |
| `OPENAI_API_KEY` | For AI-powered modules |
| `REPLICATE_API_TOKEN` | For image generation |

## Troubleshooting

```bash
# Check service logs
journalctl -u sweatpants -f

# Check if API is responding
curl -s http://localhost:8420/status | jq .

# Database issues - check permissions
ls -la /var/lib/sweatpants/

# Module not found - verify installation
sweatpants module list
ls /var/lib/sweatpants/modules/
```
