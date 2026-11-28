# Sweatpants Modules

Open-source automation modules for [Sweatpants](https://github.com/Extra-Chill/sweatpants).

## Modules

| Module | Description |
|--------|-------------|
| [agent-ping-webhook](agent-ping-webhook/) | Receive Data Machine Agent Ping webhooks and route them to AI agents via Kimaki CLI |
| [audio-transcription](audio-transcription/) | Transcribe audio files with speaker diarization using Whisper and PyAnnote |
| [font-builder](font-builder/) | Turn a letter-sheet image into OTF and TTF fonts with a PNG preview |
| [mediavine-reports](mediavine-reports/) | Export per-URL Mediavine revenue reports and deliver them via signed callbacks |

## Installation

Public modules now live here alongside the engine SDK. Install with an authenticated
`POST /modules/install` using the absolute path to `modules/<id>` on the server.
See [MONOREPO.md](../MONOREPO.md) for CI, deployment and operator setup.
History was imported with `git filter-repo --to-subdirectory-filter modules`, so `git log -- modules/<id>` shows each module's full history.

## Contributing

Each module is a self-contained directory with:
- `module.json` — Sweatpants module manifest
- `main.py` — Module entrypoint (subclasses `sweatpants.Module`)
- `README.md` — Setup and usage docs
