# Architecture Decision Records

This directory captures significant architectural and technical decisions made during the development of Earshot, along with the context and reasoning behind them.

## Format

Each ADR follows this structure:
- **Status** — Proposed, Accepted, Deprecated, or Superseded
- **Context** — The problem or situation that required a decision
- **Decision** — What was decided
- **Consequences** — Trade-offs and implications of the decision

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-opus-as-primary-audio-format.md) | Opus as primary audio storage format | Accepted |
| [0002](0002-python-venv-over-docker.md) | Python venv over Docker | Accepted |
| [0003](0003-hardware-abstraction-layer.md) | Hardware abstraction layer | Accepted |
| [0004](0004-systemd-for-service-management.md) | systemd for service management | Accepted |
| [0005](0005-local-only-no-api-sync.md) | Local-only recorder, no API sync | Accepted |
| [0006](0006-filesystem-as-state.md) | Filesystem as state, no SQLite | Accepted |
| [0007](0007-chunked-recording.md) | Chunked recording (15-minute default) | Accepted |
| [0008](0008-whisplay-hat-support.md) | Whisplay HAT as a supported audio HAT | Accepted |
| [0009](0009-ascii-art-display.md) | ASCII art for LCD display rendering | Accepted |
| [0010](0010-on-device-transcription.md) | On-device transcription with whisper.cpp | Accepted |
