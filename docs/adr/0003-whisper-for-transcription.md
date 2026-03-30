# 0003 — Whisper for Speech-to-Text

**Status:** Superseded by [ADR-0001](0001-on-device-processing.md)

## Context
Per-speaker transcription is required after diarization. A local STT model is needed to satisfy the offline-first requirement (ADR-0001).

## Decision
Use OpenAI Whisper for transcription, defaulting to the `base` model.

## Consequences
- Runs fully offline on the Pi 4B with no API key or external service required.
- The `base` model (~150MB, ~500MB RAM at runtime) balances accuracy and memory use on the Pi 4B.
- Model size is configurable — `small` can be used for better accuracy at the cost of higher RAM usage and longer processing time.
- `tiny` is available as a fallback if memory pressure becomes an issue in practice.
- Whisper accepts MP3 input directly, compatible with the chosen audio storage format (ADR-0004).
