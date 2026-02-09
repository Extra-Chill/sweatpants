# CLI Commands

Command-line interface for the Sweatpants automation engine.

## serve

Start the Sweatpants daemon.

```bash
sweatpants serve [OPTIONS]
```

**Options:**
- `--host, -h` — API host to bind to (default: `127.0.0.1`)
- `--port, -p` — API port to bind to (default: `8420`)

Initializes the database and starts the FastAPI server with uvicorn.

## status

Show engine status and running jobs.

```bash
sweatpants status
```

Displays daemon status, uptime, module count, and a table of running jobs.

## run

Start a job with the specified module.

```bash
sweatpants run <MODULE_ID> [OPTIONS]
```

**Arguments:**
- `MODULE_ID` — Module ID to run

**Options:**
- `--input, -i` — Input values as `key=value` pairs (repeatable)
- `--duration, -d` — Auto-stop after duration (e.g., `30m`, `2h`, `24h`, `7d`)

**Example:**
```bash
sweatpants run image-generator -i prompt="sunset over mountains" -d 1h
```

## stop

Stop a running job.

```bash
sweatpants stop <JOB_ID>
```

Accepts full or partial (8-character) job IDs.

## result

Get results/output for a job.

```bash
sweatpants result <JOB_ID> [OPTIONS]
```

**Options:**
- `--raw, -r` — Output raw JSON

## logs

View logs for a job.

```bash
sweatpants logs <JOB_ID> [OPTIONS]
```

**Options:**
- `--follow, -f` — Follow log output via WebSocket

## module list

List installed modules.

```bash
sweatpants module list
```

Displays a table with module ID, name, version, and capabilities.

## module install

Install a module from a local directory.

```bash
sweatpants module install <PATH>
```

The directory must contain a valid `module.json` manifest.

## module install-git

Install a module from a git repository.

```bash
sweatpants module install-git <REPO_URL> [MODULE_NAME]
```

**Arguments:**
- `REPO_URL` — Git repository URL
- `MODULE_NAME` — Subdirectory within repo containing the module (optional)

**Example:**
```bash
# Install from repo root
sweatpants module install-git https://github.com/org/my-module

# Install specific module from a monorepo
sweatpants module install-git https://github.com/org/modules image-generator
```

## module uninstall

Uninstall a module.

```bash
sweatpants module uninstall <MODULE_ID>
```

## module sync

Sync modules from configured module sources.

```bash
sweatpants module sync
```

Reads `module_sources` from `modules.yaml` and installs/updates modules from configured git repositories.

**Configuration file:** `SWEATPANTS_MODULES_CONFIG_PATH` (default: `/var/lib/sweatpants/modules.yaml`)

**Example modules.yaml:**
```yaml
module_sources:
  - repo: https://github.com/Sarai-Chinwag/sweatpants-modules
    modules:
      - diagram-generator
      - chart-generator
```
