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
| [0001](0001-on-device-processing.md) | Audio processing | Superseded by 0010 |
| [0002](0002-pyannote-for-diarization.md) | pyannote.audio for speaker diarization | Superseded by 0001 |
| [0003](0003-whisper-for-transcription.md) | Whisper for speech-to-text | Superseded by 0001 |
| [0004](0004-opus-as-primary-audio-format.md) | Opus as primary audio storage format | Accepted |
| [0005](0005-offline-first-with-api-sync.md) | Offline-first with opportunistic API sync | Superseded by 0010 |
| [0006](0006-python-venv-over-docker.md) | Python venv over Docker | Accepted |
| [0007](0007-hardware-abstraction-layer.md) | Hardware abstraction layer | Accepted |
| [0008](0008-systemd-for-service-management.md) | systemd for service management | Accepted |
| [0009](0009-sqlite-as-central-state-store.md) | SQLite as central state store | Superseded by 0011 |
| [0010](0010-local-only-no-api-sync.md) | Local-only recorder, no API sync | Accepted |
| [0011](0011-filesystem-as-state.md) | Filesystem as state, no SQLite | Accepted |
| [0012](0012-chunked-recording.md) | Chunked recording (15-minute default) | Accepted |
| [0013](0013-whisplay-hat-support.md) | Whisplay HAT as a supported audio HAT | Accepted |
| [0014](0014-ascii-art-display.md) | ASCII art for LCD display rendering | Accepted |
