# 0005 — Offline-First with Opportunistic API Sync

**Status:** Accepted

## Context
Results (MP3 + transcript) need to reach an API endpoint, but the device may operate in environments without reliable internet connectivity.

## Decision
The device operates fully offline by default. Results are always saved locally first. When internet connectivity is detected, pending results are uploaded to the configured API endpoint. Each result is only synced once.

## Consequences
- No recordings or results are ever lost due to lack of connectivity.
- Sync state must be tracked locally (e.g. a flag in `result.json` or a local database).
- The API endpoint is optional — the device is fully functional without one configured.
- Upload queue must handle retry logic for failed uploads.
- Open questions remain around retry expiry and authentication (see open-questions.md).
