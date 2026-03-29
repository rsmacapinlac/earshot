# 0009 — SQLite as Central State Store

**Status:** Accepted

## Context
The application needs to track state across several areas:

- Which recordings have been processed (and their processing lifecycle)
- Which recordings have been synced to the API (and their upload lifecycle)
- Recovery after crashes or power loss — unprocessed recordings must be detected on restart
- Partial upload failures — MP3 and result.json may need to be tracked independently

A simple flag inside `result.json` was considered for sync state, but is fragile: a crash mid-write could corrupt it, and querying across multiple recordings requires scanning the filesystem.

## Decision
Use a single SQLite database (`~/earshot/earshot.db`) as the central state store for the application.

`sqlite3` is part of the Python standard library — no additional dependency required.

### Tables

**`recordings`**
Tracks every recording and its full lifecycle.

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (UUID) | Unique recording identifier |
| `recorded_at` | TEXT (ISO 8601) | Timestamp of recording start |
| `directory` | TEXT | Path to the recording directory |
| `duration_seconds` | REAL | Length of the recording |
| `processing_state` | TEXT | `pending`, `processing`, `complete`, `failed` |
| `processing_started_at` | TEXT | Timestamp processing began |
| `processing_completed_at` | TEXT | Timestamp processing completed |
| `processing_duration_seconds` | REAL | Total processing time (for benchmarking) |
| `error` | TEXT | Error message if processing failed |

**`uploads`**
Tracks API sync state per recording, with MP3 and result.json tracked independently.

| Column | Type | Description |
|---|---|---|
| `recording_id` | TEXT | Foreign key → `recordings.id` |
| `mp3_state` | TEXT | `pending`, `uploading`, `complete`, `failed` |
| `result_state` | TEXT | `pending`, `uploading`, `complete`, `failed` |
| `retry_count` | INTEGER | Number of upload attempts |
| `last_attempted_at` | TEXT | Timestamp of last upload attempt |

**`events`**
Lightweight log of significant application events for debugging on a headless device.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment |
| `recorded_at` | TEXT (ISO 8601) | Timestamp of event |
| `recording_id` | TEXT | Associated recording (nullable) |
| `level` | TEXT | `info`, `warning`, `error` |
| `message` | TEXT | Event description |

## What SQLite Does Not Replace
- `result.json` — human-readable output artifact, stays as a file
- `audio.mp3` — binary files stay on the filesystem
- Application configuration — remains in a TOML config file for human editability

## Consequences
- On restart, unprocessed recordings are recovered with a single query (`WHERE processing_state = 'pending'`) rather than scanning the filesystem.
- Partial upload failures (TQ-7) are handled cleanly — each file has independent state.
- The `events` table provides a persistent debug log accessible via `sqlite3 ~/earshot/earshot.db`.
- SQLite has negligible overhead on Pi 4B hardware — no daemon, ~600KB library, zero idle RAM.
- The database file should be included in backup considerations alongside recordings.
- Schema migrations will need to be handled if the schema changes in future versions.
