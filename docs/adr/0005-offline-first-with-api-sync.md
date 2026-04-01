# 0005 — Offline-First with Opportunistic API Sync

**Status:** Superseded by ADR-0010

## Context

Recordings need to reach an API endpoint for processing (transcription and diarization are performed server-side per ADR-0010), but the device may operate in environments without reliable internet connectivity.

## Decision

The device operates offline by default for recording. Audio files (`audio.opus`) are always saved locally first. When internet connectivity is detected, pending recordings are uploaded to the configured API endpoint. Each recording is only synced once.

## Consequences

- No recordings are ever lost due to lack of connectivity — the MP3 is retained locally until upload succeeds.
- Sync state must be tracked locally (a flag in the `recordings` table in SQLite).
- The API endpoint is required for transcription; without one configured, the device captures audio only.
- Upload queue must handle retry logic for failed uploads.
- Open questions remain around retry expiry and authentication (see open-questions.md).
