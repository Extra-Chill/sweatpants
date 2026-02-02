# Changelog

All notable changes to Sweatpants are documented in this file.

## [0.2.4] - 2026-02-03

### Added
- Add manifest-based module management with `sweatpants module sync` command
- Add `POST /modules/sync` API endpoint for syncing modules from configured sources
- Add `modules.yaml` config file for declarative module configuration
- Support for multiple module source repositories with selective module installation

Example `modules.yaml`:
```yaml
module_sources:
  - repo: https://github.com/Sarai-Chinwag/sweatpants-modules
    modules: [diagram-generator, chart-generator]
  - repo: https://github.com/other/repo
    modules: [module-name]
```

## [0.2.3] - 2026-02-02

### Added
- Auto-discover and install modules on daemon startup. Scans SWEATPANTS_MODULES_DIR for directories containing module.json that aren't already registered.
- Add `POST /modules/install-git` API endpoint for installing modules from git repositories.
- Add `sweatpants module install-git <repo_url> [module_name]` CLI command.
- Support installing modules from subdirectories within a repo.

### Fixed
- Guard `install()` against source==dest when module already lives in modules directory.

## [0.2.2] - 2026-01-31

### Changed
- Add use_proxy parameter to browser pool

## [0.2.1] - 2026-01-30

### Changed
- Add SSL verification bypass for Bright Data proxy and initial test suite
- Add build script for homeboy integration

### Fixed
- Fix session ID format - use hex UUID without dashes for Bright Data compatibility
- Fix proxy module exports and sync version in __init__.py

## [0.2.0] - 2026-01-30

### Changed
- Integrate Bright Data proxy with IP rotation and geo-targeting
- Add --duration flag for timed job execution
- updated readme, set up changelog for initial release
- Add MIT License to the project
- Link to Homeboy repo in README
- Initial commit: Sweatpants automation engine

## [0.1.0] - 2026-01-30

### Added
- Initial release
- FastAPI REST API for job management
- CLI with Typer (serve, status, module, run, stop, logs)
- Module system with manifest-based packaging
- Job scheduler with async execution
- SQLite persistence for jobs and state
- Checkpoint/resume capability for long-running jobs
- Playwright browser pool with proxy integration
- Rotating proxy client integration
- WebSocket log streaming
- Pydantic settings with environment variable configuration
