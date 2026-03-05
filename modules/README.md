# Sweatpants Modules

Open-source automation modules for [Sweatpants](https://github.com/Extra-Chill/sweatpants).

## Modules

| Module | Description |
|--------|-------------|
| [agent-ping-webhook](agent-ping-webhook/) | Receive Data Machine Agent Ping webhooks and route them to AI agents via Kimaki CLI |
| [audio-transcription](audio-transcription/) | Transcribe audio files with speaker diarization using Whisper and PyAnnote |

## Installation

Modules are standalone — clone or copy the module directory into your Sweatpants modules path.

## Contributing

Each module is a self-contained directory with:
- `module.json` — Sweatpants module manifest
- `main.py` — Module entrypoint (subclasses `sweatpants.Module`)
- `README.md` — Setup and usage docs
