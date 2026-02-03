# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Auto-discover and install modules on daemon startup (scans modules dir for new manifests).
- Git-based module installation via `sweatpants module install-git` and `POST /modules/install-git`.
- Manifest-based module sync (`sweatpants module sync` / `POST /modules/sync`) with modules.yaml config.

### Fixed
- Guard `install()` when source already lives in modules directory.

## [0.2.3] - 2026-02-01

### Added
- OpenClaw agent skills (`skills/sweatpants`, `skills/sweatpants-module-creator`)
- Homeboy component configuration (`.homeboy.toml`)

## [0.2.2] - Previous

- Initial tracked release
