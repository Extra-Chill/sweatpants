# Changelog

All notable changes to Sweatpants are documented in this file.

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
