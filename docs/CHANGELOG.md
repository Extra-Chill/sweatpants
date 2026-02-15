# Changelog

All notable changes to Sweatpants are documented in this file.

## [0.4.3] - 2026-02-15

### Changed
- docs: add non-root systemd install example and SWEATPANTS_ENV_FILE guidance

## [0.4.2] - 2026-02-15

### Fixed
- logs --follow no longer crashes on websocket ping frames
- avoid probing .env relative to CWD; support SWEATPANTS_ENV_FILE for explicit env files

## [0.4.1] - 2026-02-15

### Added
- Add `exports_dir` setting (defaults to `<data_dir>/exports`) with `SWEATPANTS_EXPORTS_DIR` override
- Add `sweatpants config` command to show effective configuration

## [0.4.0] - 2026-02-09

### Added
- Callbacks API for orchestration - new /callbacks endpoint for receiving and tracking agent completion callbacks
- Token-based authentication for secure callback posting via X-Callback-Token header

## [0.3.2] - 2026-02-02

### Changed
- Merge pull request #7 from saraichinwag/fix/optional-proxy

### Fixed
- make proxy configuration optional at startup

## [0.3.1] - 2026-02-02

- Sync __version__ with pyproject.toml and refresh Homeboy version targets

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
